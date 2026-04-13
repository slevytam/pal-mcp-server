"""
Tests for the design_change tool MVP.
"""

import json
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from tools.design_change import DesignChangeRequest, DesignChangeTool
from utils.design_change_detection import classify_file_role, group_target_files, infer_implementation_kind


class TestDesignChangeTool:
    def setup_method(self):
        self.tool = DesignChangeTool()

    def test_tool_metadata(self):
        assert self.tool.get_name() == "design_change"
        assert "structured UI design-change patches" in self.tool.get_description()
        assert "target_file_contents" in self.tool.get_description()

    def test_schema_structure(self):
        schema = self.tool.get_input_schema()

        assert schema["type"] == "object"
        assert "change_request" in schema["required"]
        assert "target_files" in schema["required"]
        assert "mode" in schema["required"]
        assert "output_format" in schema["required"]

        properties = schema["properties"]
        assert "framework_hint" in properties
        assert "images" in properties
        assert "models" in properties
        assert "target_file_contents" in properties

    def test_request_validation_single_mode(self):
        request = DesignChangeRequest(
            change_request="Add a card",
            target_files=["/tmp/App.tsx", "/tmp/app.css"],
            mode="single",
            output_format="fragment",
        )
        assert request.mode == "single"
        assert request.framework_hint == "auto"

    def test_request_validation_consensus_requires_models(self):
        with pytest.raises(ValidationError):
            DesignChangeRequest(
                change_request="Add a card",
                target_files=["/tmp/index.html", "/tmp/styles.css", "/tmp/app.js"],
                mode="consensus",
                output_format="fragment",
            )

    def test_validate_file_paths_rejects_missing_target_files(self):
        request = DesignChangeRequest(
            change_request="Add a card",
            target_files=["/tmp/definitely-missing-home-view.tsx", "/tmp/definitely-missing-home-shell.css"],
            mode="single",
            output_format="fragment",
        )

        error = self.tool._validate_file_paths(request)
        assert error is not None
        assert "could not access the requested target_files" in error
        assert "file does not exist" in error
        assert "target_file_contents" in error

    def test_validate_file_paths_allows_inline_fallback_for_unreadable_paths(self):
        request = DesignChangeRequest(
            change_request="Add a card",
            target_files=["/tmp/home-view.tsx", "/tmp/home-shell.css"],
            target_file_contents=[
                {"path": "/tmp/home-view.tsx", "content": "<section className=\"hero\">Hero</section>"},
                {"path": "/tmp/home-shell.css", "content": ".hero { display: grid; }"},
            ],
            mode="single",
            output_format="fragment",
        )

        error = self.tool._validate_file_paths(request)
        assert error is None

    def test_detection_helpers(self):
        assert classify_file_role("/tmp/App.tsx") == "structure"
        assert classify_file_role("/tmp/styles.css") == "style"
        assert classify_file_role("/tmp/app.js") == "behavior"

        assert infer_implementation_kind(["/tmp/App.tsx", "/tmp/styles.css"]) == "react_ts"
        assert infer_implementation_kind(["/tmp/index.html", "/tmp/styles.css", "/tmp/app.js"]) == "html_css_js"

        grouped = group_target_files(["/tmp/index.html", "/tmp/styles.css", "/tmp/app.js"])
        assert grouped["structure"] == ["/tmp/index.html"]
        assert grouped["style"] == ["/tmp/styles.css"]
        assert grouped["behavior"] == ["/tmp/app.js"]

    def test_format_response_fragment_patch(self):
        request = DesignChangeRequest(
            change_request="Add a card",
            target_files=["/tmp/App.tsx", "/tmp/app.css"],
            mode="single",
            output_format="fragment",
        )
        response = {
            "status": "success",
            "implementation_kind": "react_ts",
            "patch_format": "fragment_patch",
            "summary": "Adds a metrics card.",
            "operations": [
                {
                    "id": "op_insert_card",
                    "file": "/tmp/App.tsx",
                    "file_role": "structure",
                    "kind": "insert",
                    "target": {"locator_type": "anchor_text", "value": "<section className=\"hero\">"},
                    "position": "after",
                    "content": "<section className=\"metrics-card\">New card</section>",
                },
                {
                    "id": "op_append_styles",
                    "file": "/tmp/app.css",
                    "file_role": "style",
                    "kind": "append",
                    "target": {"locator_type": "end_of_file"},
                    "position": "end",
                    "content": ".metrics-card { display: grid; }",
                },
            ],
        }

        formatted = self.tool.format_response(json.dumps(response), request)
        payload = json.loads(formatted)
        assert payload["patch_format"] == "fragment_patch"
        assert len(payload["operations"]) == 2

    def test_format_response_normalizes_live_fragment_variant(self):
        request = DesignChangeRequest(
            change_request="Add a card",
            target_files=["/tmp/home-view.tsx", "/tmp/home-shell.css"],
            mode="single",
            output_format="fragment",
        )
        response = {
            "type": "fragment_patch",
            "summary": "Adds a compact metrics panel.",
            "target_files": [
                {
                    "file": "/tmp/home-view.tsx",
                    "fragment": "return <><section className=\"hero\">Hero</section><section className=\"metrics-panel\">Metrics</section></>;",
                    "anchor_text": "return <section className=\"hero\">Hero</section>;",
                    "insert_mode": "replace",
                },
                {
                    "file": "/tmp/home-shell.css",
                    "fragment": ".metrics-panel { display: grid; }",
                    "insert_mode": "append",
                },
            ],
        }

        formatted = self.tool.format_response(json.dumps(response), request)
        payload = json.loads(formatted)
        assert payload["patch_format"] == "fragment_patch"
        assert len(payload["operations"]) == 2
        assert payload["operations"][0]["kind"] == "replace"
        assert payload["operations"][1]["kind"] == "append"

    def test_format_response_canonicalizes_append_position_in_fragment_patch(self):
        request = DesignChangeRequest(
            change_request="Add a card",
            target_files=["/tmp/home-view.tsx", "/tmp/home-shell.css"],
            mode="single",
            output_format="fragment",
        )
        response = {
            "status": "success",
            "implementation_kind": "react_ts",
            "patch_format": "fragment_patch",
            "summary": "Adds a compact metrics panel.",
            "operations": [
                {
                    "id": "op_append_styles",
                    "file": "/tmp/home-shell.css",
                    "file_role": "style",
                    "kind": "append",
                    "position": "after",
                    "target": {"locator_type": "anchor_text", "value": ".hero { display: grid; }"},
                    "content": ".metrics-panel { display: grid; }",
                }
            ],
        }

        formatted = self.tool.format_response(json.dumps(response), request)
        payload = json.loads(formatted)
        assert payload["patch_format"] == "fragment_patch"
        assert payload["operations"][0]["position"] == "end"
        assert payload["operations"][0]["target"]["locator_type"] == "end_of_file"

    def test_format_response_canonicalizes_missing_position_in_fragment_patch(self):
        request = DesignChangeRequest(
            change_request="Add a card",
            target_files=["/tmp/home-view.tsx"],
            mode="single",
            output_format="fragment",
        )
        response = {
            "status": "success",
            "implementation_kind": "react_ts",
            "patch_format": "fragment_patch",
            "summary": "Adds a compact metrics panel.",
            "operations": [
                {
                    "id": "op_replace_hero",
                    "file": "/tmp/home-view.tsx",
                    "file_role": "structure",
                    "kind": "replace",
                    "target": {"locator_type": "anchor_text", "value": "<section className=\"hero\">Hero</section>"},
                    "content": "<><section className=\"hero\">Hero</section><section className=\"metrics-panel\">Metrics</section></>",
                }
            ],
        }

        formatted = self.tool.format_response(json.dumps(response), request)
        payload = json.loads(formatted)
        assert payload["patch_format"] == "fragment_patch"
        assert payload["operations"][0]["position"] == "after"

    def test_format_response_full_file_patch(self):
        request = DesignChangeRequest(
            change_request="Update full files",
            target_files=["/tmp/index.html", "/tmp/styles.css", "/tmp/app.js"],
            mode="single",
            output_format="full_files",
        )
        response = {
            "status": "success",
            "implementation_kind": "html_css_js",
            "patch_format": "full_file_patch",
            "summary": "Adds an info panel.",
            "updated_files": [
                {
                    "file": "/tmp/index.html",
                    "file_role": "structure",
                    "content": "<html><body><aside class=\"info-panel\"></aside></body></html>",
                },
                {
                    "file": "/tmp/styles.css",
                    "file_role": "style",
                    "content": ".info-panel { padding: 16px; }",
                },
            ],
        }

        formatted = self.tool.format_response(json.dumps(response), request)
        payload = json.loads(formatted)
        assert payload["patch_format"] == "full_file_patch"
        assert len(payload["updated_files"]) == 2

    def test_format_response_rejects_unlisted_files(self):
        request = DesignChangeRequest(
            change_request="Update full files",
            target_files=["/tmp/index.html", "/tmp/styles.css"],
            mode="single",
            output_format="full_files",
        )
        response = {
            "status": "success",
            "implementation_kind": "html_css",
            "patch_format": "full_file_patch",
            "summary": "Adds an info panel.",
            "updated_files": [
                {
                    "file": "/tmp/other.css",
                    "file_role": "style",
                    "content": ".info-panel { padding: 16px; }",
                }
            ],
        }

        with pytest.raises(ValueError, match="outside target_files"):
            self.tool.format_response(json.dumps(response), request)

    def test_format_response_cannot_apply_safely(self):
        request = DesignChangeRequest(
            change_request="Add a card",
            target_files=["/tmp/App.tsx", "/tmp/app.css"],
            mode="single",
            output_format="fragment",
        )
        response = {
            "status": "cannot_apply_safely",
            "implementation_kind": "react_ts",
            "reason": "No stable insertion anchor was found.",
            "recommended_output_format": "full_files",
        }

        formatted = self.tool.format_response(json.dumps(response), request)
        payload = json.loads(formatted)
        assert payload["status"] == "cannot_apply_safely"

    def test_format_response_accepts_extra_prose_around_json(self):
        request = DesignChangeRequest(
            change_request="Update full files",
            target_files=["/tmp/index.html", "/tmp/styles.css"],
            mode="single",
            output_format="full_files",
        )
        response = (
            "Here is the requested patch.\n"
            + json.dumps(
                {
                    "status": "success",
                    "implementation_kind": "html_css",
                    "patch_format": "full_file_patch",
                    "summary": "Adds a panel.",
                    "updated_files": [
                        {
                            "file": "/tmp/index.html",
                            "file_role": "structure",
                            "content": "<main><aside>Panel</aside></main>",
                        },
                        {
                            "file": "/tmp/styles.css",
                            "file_role": "style",
                            "content": ".panel { padding: 12px; }",
                        },
                    ],
                }
            )
            + "\nUse this carefully."
        )

        formatted = self.tool.format_response(response, request)
        payload = json.loads(formatted)
        assert payload["patch_format"] == "full_file_patch"

    @pytest.mark.asyncio
    async def test_prepare_prompt_supports_consensus_mode(self):
        request = DesignChangeRequest(
            change_request="Add a card",
            target_files=["/tmp/App.tsx", "/tmp/app.css"],
            mode="consensus",
            output_format="fragment",
            models=[{"model": "gpt5"}],
        )

        prompt = await self.tool.prepare_prompt(request)
        assert "CHANGE REQUEST:" in prompt

    @pytest.mark.asyncio
    async def test_prepare_prompt_embeds_inline_target_file_contents(self):
        request = DesignChangeRequest(
            change_request="Add a card",
            target_files=["/tmp/home-view.tsx", "/tmp/home-shell.css"],
            target_file_contents=[
                {"path": "/tmp/home-view.tsx", "content": "<section className=\"hero\">Hero</section>"},
                {"path": "/tmp/home-shell.css", "content": ".hero { display: grid; }"},
            ],
            mode="single",
            output_format="fragment",
        )

        self.tool._ensure_prompt_model_context = lambda *args, **kwargs: None  # type: ignore[method-assign]
        self.tool.prepare_chat_style_prompt = lambda request, system_prompt=None: request.change_request  # type: ignore[method-assign]

        prompt = await self.tool.prepare_prompt(request)
        assert "INLINE TARGET FILE CONTENTS" in prompt
        assert "--- BEGIN FILE: /tmp/home-view.tsx ---" in prompt
        assert ".hero { display: grid; }" in prompt

    @pytest.mark.asyncio
    async def test_consensus_prompts_embed_inline_target_file_contents(self):
        request = DesignChangeRequest(
            change_request="Add a card",
            target_files=["/tmp/home-view.tsx", "/tmp/home-shell.css"],
            target_file_contents=[
                {"path": "/tmp/home-view.tsx", "content": "<section className=\"hero\">Hero</section>"},
                {"path": "/tmp/home-shell.css", "content": ".hero { display: grid; }"},
            ],
            mode="consensus",
            output_format="fragment",
            model="google/gemini-3.1-pro-preview",
            models=[{"model": "anthropic/claude-opus-4.6"}],
        )

        self.tool._ensure_prompt_model_context = lambda *args, **kwargs: None  # type: ignore[method-assign]
        self.tool.prepare_chat_style_prompt = lambda request, system_prompt=None: request.change_request  # type: ignore[method-assign]

        analysis_prompt = await self.tool._build_consensus_analysis_prompt(
            request=request,
            implementation_kind="react_ts",
            grouped_files={"structure": ["/tmp/home-view.tsx"], "style": ["/tmp/home-shell.css"], "behavior": [], "other": []},
            model_config={"model": "anthropic/claude-opus-4.6"},
            analysis_index=0,
        )
        formatter_prompt = await self.tool._build_consensus_formatter_prompt(
            request=request,
            implementation_kind="react_ts",
            grouped_files={"structure": ["/tmp/home-view.tsx"], "style": ["/tmp/home-shell.css"], "behavior": [], "other": []},
            analyses=[{"model": "anthropic/claude-opus-4.6", "stance": "neutral", "analysis": "Looks safe."}],
            formatter_model="google/gemini-3.1-pro-preview",
        )

        assert "INLINE TARGET FILE CONTENTS" in analysis_prompt
        assert "INLINE TARGET FILE CONTENTS" in formatter_prompt
        assert "--- BEGIN FILE: /tmp/home-view.tsx ---" in analysis_prompt
        assert "--- BEGIN FILE: /tmp/home-view.tsx ---" in formatter_prompt
        assert "Never omit the position field" in formatter_prompt
        assert 'position="end"' in formatter_prompt

    @pytest.mark.asyncio
    async def test_execute_consensus_returns_structured_patch(self, tmp_path):
        tool = DesignChangeTool()
        tsx_path = tmp_path / "App.tsx"
        css_path = tmp_path / "app.css"
        tsx_path.write_text("<section className=\"hero\">Hero</section>\n", encoding="utf-8")
        css_path.write_text(".hero { display: grid; }\n", encoding="utf-8")
        mocked_outputs = [
            (
                "Strong direction: add a compact card below the hero and keep styling additive.",
                {"provider": "mock-provider", "model_name": "model-a"},
            ),
            (
                "Support fragment mode if anchored to the hero section and append CSS to the end.",
                {"provider": "mock-provider", "model_name": "model-b"},
            ),
            (
                json.dumps(
                    {
                        "status": "success",
                        "implementation_kind": "react_ts",
                        "patch_format": "fragment_patch",
                        "summary": "Adds a compact metrics card.",
                        "operations": [
                            {
                                "id": "op_insert_card",
                                "file": str(tsx_path),
                                "file_role": "structure",
                                "kind": "insert",
                                "target": {
                                    "locator_type": "anchor_text",
                                    "value": "<section className=\"hero\">",
                                },
                                "position": "after",
                                "content": "<section className=\"metrics-card\">Card</section>",
                            },
                            {
                                "id": "op_append_styles",
                                "file": str(css_path),
                                "file_role": "style",
                                "kind": "append",
                                "target": {"locator_type": "end_of_file"},
                                "position": "end",
                                "content": ".metrics-card { padding: 16px; }",
                            },
                        ],
                    }
                ),
                {"provider": "mock-provider", "model_name": "model-a"},
            ),
        ]

        async def fake_generate(*args, **kwargs):
            return mocked_outputs.pop(0)

        tool._generate_model_response = fake_generate  # type: ignore[method-assign]
        tool._ensure_prompt_model_context = lambda *args, **kwargs: None  # type: ignore[method-assign]
        tool.prepare_chat_style_prompt = lambda request, system_prompt=None: request.change_request  # type: ignore[method-assign]
        tool._create_continuation_offer = Mock(return_value=None)

        result = await tool.execute(
            {
                "change_request": "Add a compact metrics card below the hero",
                "target_files": [str(tsx_path), str(css_path)],
                "mode": "consensus",
                "output_format": "fragment",
                "models": [{"model": "model-a"}, {"model": "model-b", "stance": "for"}],
            }
        )

        payload = json.loads(result[0].text)
        assert payload["status"] == "success"
        assert payload["metadata"]["consensus_mode"] is True
        assert payload["metadata"]["consensus_models"] == ["model-a", "model-b"]
        inner = json.loads(payload["content"])
        assert inner["patch_format"] == "fragment_patch"
