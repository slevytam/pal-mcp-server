"""
Design change tool - structured UI patch generation for existing implementations.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from mcp.types import TextContent
from pydantic import BaseModel, Field, model_validator

from systemprompts.design_change_prompt import DESIGN_CHANGE_PROMPT
from tools.models import ToolModelCategory, ToolOutput
from tools.shared.exceptions import ToolExecutionError
from tools.shared.base_models import COMMON_FIELD_DESCRIPTIONS
from tools.simple.base import SimpleTool
from utils.design_change_detection import group_target_files, infer_implementation_kind
from utils.file_utils import resolve_and_validate_path
from utils.design_change_models import (
    CannotApplySafelyResponse,
    FragmentPatchResponse,
    FullFilePatchResponse,
)

DesignMode = Literal["single", "consensus"]
OutputFormat = Literal["fragment", "full_files"]


class DesignChangeRequest(BaseModel):
    """Request model for the design change tool."""

    change_request: str = Field(..., description="Requested UI/design change to make.")
    target_files: list[str] = Field(..., description="Absolute file paths for structure/style/behavior files.")
    mode: DesignMode = Field(default="single", description="Whether to use one model or a consensus workflow.")
    output_format: OutputFormat = Field(
        default="fragment",
        description="Return a fragment patch or a full file patch.",
    )
    framework_hint: str | None = Field(
        default="auto",
        description="Optional override such as react_ts, react_js, html_css, html_css_js.",
    )
    model: str | None = Field(None, description=COMMON_FIELD_DESCRIPTIONS["model"])
    models: list[dict] | None = Field(
        default=None,
        description="Optional model roster for consensus mode.",
    )
    temperature: float | None = Field(None, description=COMMON_FIELD_DESCRIPTIONS["temperature"])
    thinking_mode: str | None = Field(None, description=COMMON_FIELD_DESCRIPTIONS["thinking_mode"])
    images: list[str] = Field(default_factory=list, description=COMMON_FIELD_DESCRIPTIONS["images"])
    continuation_id: str | None = Field(None, description=COMMON_FIELD_DESCRIPTIONS["continuation_id"])

    @model_validator(mode="after")
    def validate_mode_specific_fields(self):
        if self.mode == "single" and self.models:
            raise ValueError("'models' is only valid when mode='consensus'")
        if self.mode == "consensus" and not self.models:
            raise ValueError("'models' is required when mode='consensus'")
        return self


class DesignChangeTool(SimpleTool):
    """Generate structured UI patches for TSX/CSS and HTML/CSS/JS style projects."""

    def get_name(self) -> str:
        return "design_change"

    def get_description(self) -> str:
        return (
            "Generate structured UI design-change patches for existing implementations such as "
            "TSX/CSS or HTML/CSS/JS. Supports fragment patches and full-file patches."
        )

    def get_system_prompt(self) -> str:
        return DESIGN_CHANGE_PROMPT

    def get_default_temperature(self) -> float:
        return 0.2

    def get_model_category(self) -> ToolModelCategory:
        return ToolModelCategory.BALANCED

    def get_request_model(self):
        return DesignChangeRequest

    def get_tool_fields(self) -> dict[str, dict[str, Any]]:
        return {
            "change_request": {
                "type": "string",
                "description": "Requested UI/design change to make.",
            },
            "target_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Absolute paths to structure/style/behavior files.",
            },
            "mode": {
                "type": "string",
                "enum": ["single", "consensus"],
                "description": "Whether to use one model or a consensus workflow.",
            },
            "output_format": {
                "type": "string",
                "enum": ["fragment", "full_files"],
                "description": "Return a fragment patch or full updated files.",
            },
            "framework_hint": {
                "type": "string",
                "description": "Optional override such as react_ts, react_js, html_css, html_css_js.",
            },
            "models": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Optional model roster for consensus mode.",
            },
            "images": self.IMAGES_FIELD,
            "continuation_id": {
                "type": "string",
                "description": COMMON_FIELD_DESCRIPTIONS["continuation_id"],
            },
        }

    def get_required_fields(self) -> list[str]:
        return ["change_request", "target_files", "mode", "output_format"]

    def _validate_file_paths(self, request) -> str | None:
        path_error = super()._validate_file_paths(request)
        if path_error:
            return path_error

        unreadable_files: list[str] = []
        for file_path in self.get_request_files(request):
            try:
                resolved_path = resolve_and_validate_path(file_path)
            except (PermissionError, ValueError) as exc:
                unreadable_files.append(f"{file_path} ({exc})")
                continue

            if not resolved_path.exists():
                unreadable_files.append(f"{file_path} (file does not exist)")
            elif not resolved_path.is_file():
                unreadable_files.append(f"{file_path} (path is not a file)")

        if unreadable_files:
            joined = "\n".join(f"- {entry}" for entry in unreadable_files)
            return (
                "Error: design_change could not access the requested target_files.\n"
                "Each target file must be a readable absolute path to an existing file.\n"
                f"{joined}"
            )

        return None

    def get_request_prompt(self, request) -> str:
        return request.change_request

    def get_request_files(self, request) -> list:
        return request.target_files

    def set_request_files(self, request, files: list) -> None:
        request.target_files = files

    async def prepare_prompt(self, request: DesignChangeRequest) -> str:
        self._ensure_prompt_model_context(request)
        implementation_kind = infer_implementation_kind(request.target_files, request.framework_hint)
        grouped_files = group_target_files(request.target_files)

        request.change_request = (
            f"CHANGE REQUEST:\n{request.change_request}\n\n"
            f"MODE: {request.mode}\n"
            f"OUTPUT FORMAT: {request.output_format}\n"
            f"IMPLEMENTATION KIND: {implementation_kind}\n\n"
            f"TARGET FILES:\n" + "\n".join(request.target_files) + "\n\n"
            f"{self._build_implementation_instructions(implementation_kind, request.output_format, grouped_files)}"
        )
        return self.prepare_chat_style_prompt(request, system_prompt=self.get_system_prompt())

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        if arguments.get("mode") != "consensus":
            return await super().execute(arguments)

        self._current_arguments = arguments
        request = self.get_request_model()(**arguments)

        path_error = self._validate_file_paths(request)
        if path_error:
            raise ToolExecutionError(ToolOutput(status="error", content=path_error, content_type="text").model_dump_json())

        try:
            formatted_response, formatter_info, metadata = await self._execute_consensus(request, arguments)
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(
                ToolOutput(
                    status="error",
                    content=f"Error in {self.get_name()}: {str(exc)}",
                    content_type="text",
                ).model_dump_json()
            ) from exc

        continuation_id = self.get_request_continuation_id(request)
        if continuation_id:
            self._record_assistant_turn(continuation_id, formatted_response, request, formatter_info)

        continuation_data = self._create_continuation_offer(request, formatter_info)
        if continuation_data:
            tool_output = self._create_continuation_offer_response(
                formatted_response,
                continuation_data,
                request,
                formatter_info,
            )
            tool_output.metadata = {**(tool_output.metadata or {}), **metadata}
        else:
            tool_output = ToolOutput(
                status="success",
                content=formatted_response,
                content_type="text",
                metadata=metadata,
            )

        return [TextContent(type="text", text=tool_output.model_dump_json())]

    def format_response(self, response: str, request: DesignChangeRequest, model_info: dict | None = None) -> str:
        payload = self._normalize_payload(self._extract_json_object(response), request)

        if payload.get("status") == "cannot_apply_safely":
            validated = CannotApplySafelyResponse.model_validate(payload)
        elif payload.get("patch_format") == "fragment_patch":
            validated = FragmentPatchResponse.model_validate(payload)
            self._validate_response_files(
                request.target_files,
                [operation.file for operation in validated.operations],
            )
        elif payload.get("patch_format") == "full_file_patch":
            validated = FullFilePatchResponse.model_validate(payload)
            self._validate_response_files(
                request.target_files,
                [updated.file for updated in validated.updated_files],
            )
        else:
            snippet = response.strip().replace("\n", " ")[:600]
            raise ValueError(
                "Model response did not match a supported design_change response shape. "
                f"Raw response snippet: {snippet}"
            )

        return validated.model_dump_json()

    def _normalize_payload(self, payload: dict[str, Any], request: DesignChangeRequest) -> dict[str, Any]:
        if "patch_format" in payload or payload.get("status") == "cannot_apply_safely":
            return payload

        nested_full_file_patch = payload.get("full_file_patch")
        if isinstance(nested_full_file_patch, dict):
            files = nested_full_file_patch.get("files", [])
            normalized = self._normalize_full_file_entries(files, request)
            if normalized:
                return {
                    "status": "success",
                    "implementation_kind": infer_implementation_kind(request.target_files, request.framework_hint),
                    "patch_format": "full_file_patch",
                    "summary": payload.get("summary")
                    or nested_full_file_patch.get("summary")
                    or payload.get("change_summary")
                    or "Generated full-file patch from consensus formatter output.",
                    "updated_files": normalized,
                }

        file_edits = payload.get("file_edits")
        if isinstance(file_edits, list):
            normalized = self._normalize_full_file_entries(file_edits, request)
            if normalized:
                return {
                    "status": "success",
                    "implementation_kind": infer_implementation_kind(request.target_files, request.framework_hint),
                    "patch_format": "full_file_patch",
                    "summary": payload.get("summary")
                    or payload.get("change_summary")
                    or "Generated full-file patch from formatter file_edits output.",
                    "updated_files": normalized,
                }

        target_files = payload.get("target_files")
        if isinstance(target_files, dict):
            implementation_kind = infer_implementation_kind(request.target_files, request.framework_hint)
            normalized_files = self._normalize_target_file_mapping(target_files, request)
            if normalized_files:
                return {
                    "status": "success",
                    "implementation_kind": implementation_kind,
                    "patch_format": "full_file_patch",
                    "summary": payload.get("summary")
                    or payload.get("change_summary")
                    or "Generated full-file patch from consensus formatter output.",
                    "updated_files": normalized_files,
                }

        return payload

    def _normalize_target_file_mapping(
        self,
        target_files: dict[str, Any],
        request: DesignChangeRequest,
    ) -> list[dict[str, str]]:
        grouped_files = group_target_files(request.target_files)
        style_files = set(grouped_files["style"])
        behavior_files = set(grouped_files["behavior"])
        normalized_files: list[dict[str, str]] = []

        for file_path, content in target_files.items():
            if not isinstance(file_path, str) or not isinstance(content, str):
                continue
            if file_path in style_files:
                file_role = "style"
            elif file_path in behavior_files:
                file_role = "behavior"
            else:
                file_role = "structure"
            normalized_files.append(
                {
                    "file": file_path,
                    "file_role": file_role,
                    "content": content,
                }
            )
        return normalized_files

    def _normalize_full_file_entries(
        self,
        files: list[Any],
        request: DesignChangeRequest,
    ) -> list[dict[str, str]]:
        grouped_files = group_target_files(request.target_files)
        style_files = set(grouped_files["style"])
        behavior_files = set(grouped_files["behavior"])
        normalized_files: list[dict[str, str]] = []

        for entry in files:
            if not isinstance(entry, dict):
                continue
            file_path = entry.get("file") or entry.get("file_path")
            content = entry.get("content") or entry.get("file_content") or entry.get("patch_content")
            if not isinstance(file_path, str) or not isinstance(content, str):
                continue
            if file_path in style_files:
                file_role = "style"
            elif file_path in behavior_files:
                file_role = "behavior"
            else:
                file_role = "structure"
            normalized_files.append(
                {
                    "file": file_path,
                    "file_role": file_role,
                    "content": content,
                }
            )

        return normalized_files

    async def _execute_consensus(
        self,
        request: DesignChangeRequest,
        arguments: dict[str, Any],
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        implementation_kind = infer_implementation_kind(request.target_files, request.framework_hint)
        grouped_files = group_target_files(request.target_files)

        analyses: list[dict[str, Any]] = []
        consulted_models: list[str] = []

        for index, model_config in enumerate(request.models or []):
            model_name = model_config.get("model")
            if not model_name:
                raise ValueError("Each consensus model entry must include a model")

            prompt_text = await self._build_consensus_analysis_prompt(
                request=request,
                implementation_kind=implementation_kind,
                grouped_files=grouped_files,
                model_config=model_config,
                analysis_index=index,
            )
            raw_response, _ = await self._generate_model_response(
                model_name=model_name,
                prompt_text=prompt_text,
                request=request,
                arguments=arguments,
            )
            analyses.append(
                {
                    "model": model_name,
                    "stance": model_config.get("stance", "neutral"),
                    "analysis": raw_response.strip(),
                }
            )
            consulted_models.append(model_name)

        formatter_model = request.model or consulted_models[0]
        formatter_prompt = await self._build_consensus_formatter_prompt(
            request=request,
            implementation_kind=implementation_kind,
            grouped_files=grouped_files,
            analyses=analyses,
            formatter_model=formatter_model,
        )
        final_raw_response, formatter_info = await self._generate_model_response(
            model_name=formatter_model,
            prompt_text=formatter_prompt,
            request=request,
            arguments=arguments,
        )
        formatted_response = self.format_response(final_raw_response, request, formatter_info)

        metadata = {
            "consensus_mode": True,
            "consensus_models": consulted_models,
            "formatter_model": formatter_model,
        }
        if formatter_info.get("provider"):
            provider = formatter_info["provider"]
            if isinstance(provider, str):
                metadata["provider_used"] = provider
            else:
                metadata["provider_used"] = provider.get_provider_type().value
        metadata["model_used"] = formatter_model

        return formatted_response, formatter_info, metadata

    async def _build_consensus_analysis_prompt(
        self,
        request: DesignChangeRequest,
        implementation_kind: str,
        grouped_files: dict[str, list[str]],
        model_config: dict[str, Any],
        analysis_index: int,
    ) -> str:
        stance = model_config.get("stance", "neutral")
        stance_prompt = model_config.get("stance_prompt", "")
        analysis_request = request.model_copy(
            update={
                "change_request": (
                    f"CONSENSUS ANALYSIS STEP {analysis_index + 1}\n"
                    f"Change request: {request.change_request}\n\n"
                    f"Implementation kind: {implementation_kind}\n"
                    f"Output format target: {request.output_format}\n"
                    f"Structure files: {grouped_files['structure']}\n"
                    f"Style files: {grouped_files['style']}\n"
                    f"Behavior files: {grouped_files['behavior']}\n\n"
                    f"Provide a concise design recommendation from a {stance} perspective.\n"
                    "Focus on visual direction, integration risk, and whether fragment mode appears safe.\n"
                    "Do not return JSON. Do not return a patch. Keep the response under 350 words.\n"
                    f"{stance_prompt}"
                )
            }
        )
        self._ensure_prompt_model_context(analysis_request, preferred_model=model_config.get("model"))
        return self.prepare_chat_style_prompt(analysis_request, system_prompt=self.get_system_prompt())

    async def _build_consensus_formatter_prompt(
        self,
        request: DesignChangeRequest,
        implementation_kind: str,
        grouped_files: dict[str, list[str]],
        analyses: list[dict[str, Any]],
        formatter_model: str,
    ) -> str:
        analysis_text = "\n\n".join(
            [
                f"MODEL: {analysis['model']}\nSTANCE: {analysis['stance']}\nANALYSIS:\n{analysis['analysis']}"
                for analysis in analyses
            ]
        )
        formatter_request = request.model_copy(
            update={
                "change_request": (
                    f"CONSENSUS FORMATTER\n"
                    f"Primary change request: {request.change_request}\n\n"
                    f"Implementation kind: {implementation_kind}\n"
                    f"Desired output format: {request.output_format}\n"
                    f"Formatter model: {formatter_model}\n"
                    f"Structure files: {grouped_files['structure']}\n"
                    f"Style files: {grouped_files['style']}\n"
                    f"Behavior files: {grouped_files['behavior']}\n\n"
                    "Synthesize the consensus analyses below into a single structured patch response.\n"
                    "RESPOND WITH EXACTLY ONE JSON OBJECT AND NOTHING ELSE.\n"
                    "NO markdown fences.\n"
                    "NO commentary before or after JSON.\n"
                    "NO alternative field names.\n"
                    "Responses that do not match this schema are unusable and will be rejected.\n\n"
                    "You MUST return exactly one of these shapes:\n\n"
                    "1. full_file_patch response:\n"
                    "{\n"
                    '  "status": "success",\n'
                    f'  "implementation_kind": "{implementation_kind}",\n'
                    '  "patch_format": "full_file_patch",\n'
                    '  "summary": "Short summary",\n'
                    '  "updated_files": [\n'
                    "    {\n"
                    '      "file": "/absolute/path/to/file",\n'
                    '      "file_role": "structure",\n'
                    '      "content": "complete file contents"\n'
                    "    }\n"
                    "  ]\n"
                    "}\n\n"
                    "2. fragment_patch response:\n"
                    "{\n"
                    '  "status": "success",\n'
                    f'  "implementation_kind": "{implementation_kind}",\n'
                    '  "patch_format": "fragment_patch",\n'
                    '  "summary": "Short summary",\n'
                    '  "operations": [\n'
                    "    {\n"
                    '      "id": "op_1",\n'
                    '      "file": "/absolute/path/to/file",\n'
                    '      "file_role": "structure",\n'
                    '      "kind": "insert",\n'
                    '      "target": {"locator_type": "anchor_text", "value": "<section className=\\"hero\\">"},\n'
                    '      "position": "after",\n'
                    '      "content": "<section className=\\"metrics-panel\\">...</section>"\n'
                    "    }\n"
                    "  ]\n"
                    "}\n\n"
                    "3. cannot_apply_safely response:\n"
                    "{\n"
                    '  "status": "cannot_apply_safely",\n'
                    f'  "implementation_kind": "{implementation_kind}",\n'
                    '  "reason": "Explain why fragment or file patch could not be produced safely",\n'
                    '  "recommended_output_format": "full_files"\n'
                    "}\n\n"
                    "CRITICAL FIELD RULES:\n"
                    '- Use "updated_files", never "target_files", "file_edits", or nested "full_file_patch".\n'
                    '- Use "file", never "file_path".\n'
                    '- Use "content", never "file_content" or "patch_content".\n'
                    '- Only reference files from the provided target file list.\n'
                    '- If you choose full_file_patch, each entry must contain complete file contents.\n'
                    '- If you choose fragment_patch, each operation must use the exact field names shown above.\n'
                    '- If fragment mode is too risky based on the analyses, return cannot_apply_safely.\n\n'
                    f"{analysis_text}"
                )
            }
        )
        self._ensure_prompt_model_context(formatter_request, preferred_model=formatter_model)
        return self.prepare_chat_style_prompt(formatter_request, system_prompt=self.get_system_prompt())

    async def _generate_model_response(
        self,
        model_name: str,
        prompt_text: str,
        request: DesignChangeRequest,
        arguments: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if arguments.get("_model_context") is not None and arguments.get("_resolved_model_name") == model_name:
            model_context = arguments["_model_context"]
        else:
            from utils.model_context import ModelContext

            model_context = ModelContext(model_name)

        self._model_context = model_context
        self._current_model_name = model_name

        provider = model_context.provider
        capabilities = model_context.capabilities
        temperature = request.temperature if request.temperature is not None else self.get_default_temperature()
        temperature, _warnings = self.validate_and_correct_temperature(temperature, model_context)
        thinking_mode = request.thinking_mode or self.get_default_thinking_mode()

        system_prompt = self.get_language_instruction() + self._augment_system_prompt_with_capabilities(
            self.get_system_prompt(), capabilities
        )
        supports_thinking = capabilities.supports_extended_thinking

        model_response = provider.generate_content(
            prompt=prompt_text,
            model_name=model_name,
            system_prompt=system_prompt,
            temperature=temperature,
            thinking_mode=thinking_mode if supports_thinking else None,
            images=request.images if request.images else None,
        )
        if not model_response.content:
            finish_reason = (model_response.metadata or {}).get("finish_reason", "Unknown")
            raise ValueError(f"Model '{model_name}' returned empty response. Finish reason: {finish_reason}")

        model_info = {
            "provider": provider,
            "model_name": model_name,
            "model_response": model_response,
        }
        return model_response.content, model_info

    def _ensure_prompt_model_context(
        self,
        request: DesignChangeRequest,
        preferred_model: str | None = None,
    ) -> None:
        if getattr(self, "_model_context", None) is not None and getattr(self, "_current_model_name", None):
            return

        model_name = preferred_model or request.model
        if not model_name and request.models:
            model_name = request.models[0].get("model")
        if not model_name:
            from config import DEFAULT_MODEL

            model_name = DEFAULT_MODEL

        if self._should_require_model_selection(model_name):
            raise ValueError(self._build_auto_mode_required_message())

        from utils.model_context import ModelContext

        self._current_model_name = model_name
        self._model_context = ModelContext(model_name)

    @staticmethod
    def _validate_response_files(target_files: list[str], response_files: list[str]) -> None:
        unexpected = sorted({path for path in response_files if path not in target_files})
        if unexpected:
            raise ValueError(f"Response referenced files outside target_files: {unexpected}")

    @staticmethod
    def _extract_json_object(response: str) -> dict[str, Any]:
        response = response.strip()

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        for index, char in enumerate(response):
            if char != "{":
                continue
            try:
                payload, end = decoder.raw_decode(response[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
            break

        raise ValueError("Response did not contain a valid JSON object")

    @staticmethod
    def _build_implementation_instructions(
        implementation_kind: str,
        output_format: str,
        grouped_files: dict[str, list[str]],
    ) -> str:
        lines = [
            "IMPLEMENTATION RULES:",
            f"- Structure files: {grouped_files['structure']}",
            f"- Style files: {grouped_files['style']}",
            f"- Behavior files: {grouped_files['behavior']}",
        ]

        if implementation_kind == "react_ts":
            lines.extend(
                [
                    "- Preserve existing React and TypeScript conventions.",
                    "- Return TSX compatible with the surrounding component.",
                    "- Preserve import style, prop typing, and local component patterns.",
                ]
            )
        elif implementation_kind == "react_js":
            lines.extend(
                [
                    "- Preserve existing React JavaScript conventions.",
                    "- Return JSX compatible with the surrounding component.",
                ]
            )
        elif implementation_kind in {"html_css", "html_css_js", "html_css_ts"}:
            lines.extend(
                [
                    "- Preserve existing HTML structure and class naming patterns.",
                    "- Keep CSS additive and scoped where possible.",
                    "- Only include JS or TS behavior changes if the request requires interaction.",
                ]
            )
        else:
            lines.append("- Implementation kind is unknown; only respond if the provided files are still sufficient.")

        if output_format == "fragment":
            lines.extend(
                [
                    "- Return a fragment_patch only if it can be applied safely.",
                    "- Use stable anchor_text targets for structure insertions.",
                ]
            )
        else:
            lines.append("- Return a full_file_patch with complete contents for changed target files only.")

        return "\n".join(lines)
