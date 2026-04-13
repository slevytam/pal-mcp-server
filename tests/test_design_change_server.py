"""
Server-level tests for design_change tool registration and routing.
"""

import json
from unittest.mock import AsyncMock

import pytest
from mcp.types import TextContent

import server
from tools.models import ToolOutput


class TestDesignChangeServerIntegration:
    @pytest.mark.asyncio
    async def test_handle_call_tool_routes_design_change(self, monkeypatch):
        mocked_tool = server.TOOLS["design_change"]
        original_execute = mocked_tool.execute
        mocked_tool.execute = AsyncMock(
            return_value=[
                TextContent(
                    type="text",
                    text=ToolOutput(
                        status="success",
                        content=json.dumps(
                            {
                                "status": "success",
                                "implementation_kind": "react_ts",
                                "patch_format": "fragment_patch",
                                "summary": "Adds an alert card.",
                                "operations": [],
                            }
                        ),
                        content_type="json",
                    ).model_dump_json(),
                )
            ]
        )

        try:
            result = await server.handle_call_tool(
                "design_change",
                {
                    "change_request": "Add an alert card",
                    "target_files": ["/tmp/App.tsx", "/tmp/app.css"],
                    "mode": "single",
                    "output_format": "fragment",
                    "model": "flash",
                },
            )
        finally:
            mocked_tool.execute = original_execute

        assert len(result) == 1
        payload = json.loads(result[0].text)
        assert payload["status"] == "success"

    @pytest.mark.asyncio
    async def test_prompt_list_includes_design_change_tools(self):
        prompts = await server.handle_list_prompts()
        prompt_names = {prompt.name for prompt in prompts}

        assert "design_change" in prompt_names
        assert "design_change_apply" in prompt_names

    def test_design_change_prompt_template_mentions_inline_fallback(self):
        template_info = server.PROMPT_TEMPLATES["design_change"]

        assert "target_file_contents" in template_info["description"]
        assert "target_file_contents" in template_info["template"]
