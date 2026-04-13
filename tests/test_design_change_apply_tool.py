"""
Tests for the design_change_apply MCP tool.
"""

import json

import pytest

from tools.design_change_apply import DesignChangeApplyTool


class TestDesignChangeApplyTool:
    @pytest.fixture
    def tool(self):
        return DesignChangeApplyTool()

    @pytest.mark.asyncio
    async def test_execute_full_file_patch_dry_run(self, tool, tmp_path):
        html_file = tmp_path / "index.html"
        html_file.write_text("<div>Old</div>\n", encoding="utf-8")

        result = await tool.execute(
            {
                "patch": {
                    "status": "success",
                    "implementation_kind": "html_css",
                    "patch_format": "full_file_patch",
                    "summary": "Update html file.",
                    "updated_files": [
                        {
                            "file": str(html_file),
                            "file_role": "structure",
                            "content": "<div>New</div>\n",
                        }
                    ],
                },
                "allowed_files": [str(html_file)],
                "dry_run": True,
            }
        )

        payload = json.loads(result[0].text)
        assert payload["status"] == "success"
        inner = json.loads(payload["content"])
        assert inner["status"] == "dry_run"
        assert inner["would_modify_files"] == [str(html_file)]
