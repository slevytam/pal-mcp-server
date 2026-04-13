"""
Design change apply tool - apply validated UI patch payloads.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.types import TextContent
from pydantic import BaseModel, Field

from tools.models import ToolOutput
from tools.shared.base_models import COMMON_FIELD_DESCRIPTIONS
from tools.shared.base_tool import BaseTool
from utils.design_change_apply import apply_fragment_patch, apply_full_file_patch
from utils.design_change_models import FragmentPatchResponse, FullFilePatchResponse


class DesignChangeApplyRequest(BaseModel):
    """Request model for applying structured design patches."""

    patch: dict[str, Any] = Field(..., description="Validated design_change patch payload to apply or dry-run.")
    allowed_files: list[str] | None = Field(
        default=None,
        description="Optional allowlist of absolute file paths that the patch may touch.",
    )
    dry_run: bool = Field(default=True, description="When true, validate and simulate without writing files.")
    continuation_id: str | None = Field(None, description=COMMON_FIELD_DESCRIPTIONS["continuation_id"])


class DesignChangeApplyTool(BaseTool):
    """Thin MCP wrapper around the design change apply helpers."""

    def get_name(self) -> str:
        return "design_change_apply"

    def get_description(self) -> str:
        return (
            "Apply or dry-run structured design_change patch payloads. Supports both fragment patches "
            "and full-file patches."
        )

    def get_annotations(self) -> dict[str, Any]:
        return {"readOnlyHint": False}

    def requires_model(self) -> bool:
        return False

    def get_system_prompt(self) -> str:
        """No AI model needed for this tool."""
        return ""

    def get_request_model(self):
        """Return the Pydantic request model for direct validation."""
        return DesignChangeApplyRequest

    async def prepare_prompt(self, request: DesignChangeApplyRequest) -> str:
        """Not used for this utility tool."""
        return ""

    def format_response(self, response: str, request: DesignChangeApplyRequest, model_info: dict | None = None) -> str:
        """Not used for this utility tool."""
        return response

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "patch": {
                    "type": "object",
                    "description": "Validated design_change patch payload to apply or dry-run.",
                },
                "allowed_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional allowlist of absolute file paths that the patch may touch.",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "When true, validate and simulate without writing files.",
                },
                "continuation_id": {
                    "type": "string",
                    "description": COMMON_FIELD_DESCRIPTIONS["continuation_id"],
                },
            },
            "required": ["patch"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        request = DesignChangeApplyRequest(**arguments)
        patch_payload = request.patch
        allowed_files = set(request.allowed_files) if request.allowed_files is not None else None

        patch_format = patch_payload.get("patch_format")
        if patch_format == "fragment_patch":
            patch = FragmentPatchResponse.model_validate(patch_payload)
            result = apply_fragment_patch(patch, allowed_files=allowed_files, dry_run=request.dry_run)
        elif patch_format == "full_file_patch":
            patch = FullFilePatchResponse.model_validate(patch_payload)
            result = apply_full_file_patch(patch, allowed_files=allowed_files, dry_run=request.dry_run)
        else:
            error_output = ToolOutput(
                status="error",
                content="Patch payload must include patch_format='fragment_patch' or 'full_file_patch'",
                content_type="text",
            )
            raise ValueError(error_output.model_dump_json())

        tool_output = ToolOutput(
            status="success",
            content=json.dumps(result),
            content_type="json",
        )
        return [TextContent(type="text", text=tool_output.model_dump_json())]
