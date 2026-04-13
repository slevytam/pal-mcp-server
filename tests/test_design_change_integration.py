"""Integration test for design_change consensus using OpenRouter models."""

from __future__ import annotations

import json
import os

import pytest

from providers.registry import ModelProviderRegistry
from providers.shared import ProviderType
from tools.design_change import DesignChangeTool


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.no_mock_provider
async def test_design_change_consensus_with_openrouter(monkeypatch, tmp_path):
    """Exercise design_change consensus end-to-end with low-cost OpenRouter models."""

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not openrouter_key or openrouter_key.startswith("dummy"):
        pytest.skip("OPENROUTER_API_KEY not configured for live OpenRouter integration test.")

    tsx_file = tmp_path / "Dashboard.tsx"
    css_file = tmp_path / "dashboard.css"
    tsx_file.write_text(
        (
            "export function Dashboard() {\n"
            "  return (\n"
            "    <main>\n"
            "      <section className=\"hero\">Hero</section>\n"
            "    </main>\n"
            "  );\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    css_file.write_text(".hero { display: block; }\n", encoding="utf-8")

    with monkeypatch.context() as m:
        m.setenv("OPENROUTER_API_KEY", openrouter_key)
        m.setenv("DEFAULT_MODEL", "auto")
        m.setenv("OPENROUTER_ALLOWED_MODELS", "flash,mistral")

        for key in [
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "XAI_API_KEY",
            "DIAL_API_KEY",
            "CUSTOM_API_KEY",
            "CUSTOM_API_URL",
        ]:
            m.delenv(key, raising=False)

        import utils.model_restrictions as model_restrictions
        from providers.openrouter import OpenRouterProvider

        model_restrictions._restriction_service = None
        ModelProviderRegistry.reset_for_testing()
        ModelProviderRegistry.register_provider(ProviderType.OPENROUTER, OpenRouterProvider)

        tool = DesignChangeTool()
        result = await tool.execute(
            {
                "change_request": (
                    "Add a compact metrics panel directly below the hero section. "
                    "Keep styling additive and aligned with the existing simple dashboard aesthetic."
                ),
                "target_files": [str(tsx_file), str(css_file)],
                "mode": "consensus",
                "output_format": "full_files",
                "model": "flash",
                "models": [
                    {"model": "flash", "stance": "neutral"},
                    {"model": "mistral", "stance": "against"},
                ],
            }
        )

    assert result and result[0].type == "text"
    payload = json.loads(result[0].text)
    assert payload["status"] in {"success", "continuation_available"}
    assert payload["metadata"]["consensus_mode"] is True
    assert payload["metadata"]["formatter_model"] == "flash"

    inner = json.loads(payload["content"])
    assert inner["implementation_kind"] == "react_ts"

    if inner["status"] == "cannot_apply_safely":
        assert inner["reason"]
    elif inner["patch_format"] == "full_file_patch":
        updated_files = {entry["file"]: entry["content"] for entry in inner["updated_files"]}
        assert str(tsx_file) in updated_files
        assert str(css_file) in updated_files
    else:
        assert inner["status"] == "success"
        assert inner["patch_format"] == "fragment_patch"
        assert inner["operations"]

    ModelProviderRegistry.reset_for_testing()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.no_mock_provider
async def test_design_change_fragment_consensus_with_openrouter(monkeypatch, tmp_path):
    """Exercise fragment-mode consensus formatting against cheap OpenRouter models."""

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not openrouter_key or openrouter_key.startswith("dummy"):
        pytest.skip("OPENROUTER_API_KEY not configured for live OpenRouter integration test.")

    tsx_file = tmp_path / "Dashboard.tsx"
    css_file = tmp_path / "dashboard.css"
    tsx_file.write_text(
        (
            "export function Dashboard() {\n"
            "  return (\n"
            "    <main>\n"
            "      <section className=\"hero\">Hero</section>\n"
            "      <section className=\"stats-grid\"></section>\n"
            "    </main>\n"
            "  );\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    css_file.write_text(
        ".hero { display: block; }\n.stats-grid { display: grid; gap: 12px; }\n",
        encoding="utf-8",
    )

    with monkeypatch.context() as m:
        m.setenv("OPENROUTER_API_KEY", openrouter_key)
        m.setenv("DEFAULT_MODEL", "auto")
        m.setenv("OPENROUTER_ALLOWED_MODELS", "flash,mistral")

        for key in [
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "XAI_API_KEY",
            "DIAL_API_KEY",
            "CUSTOM_API_KEY",
            "CUSTOM_API_URL",
        ]:
            m.delenv(key, raising=False)

        import utils.model_restrictions as model_restrictions
        from providers.openrouter import OpenRouterProvider

        model_restrictions._restriction_service = None
        ModelProviderRegistry.reset_for_testing()
        ModelProviderRegistry.register_provider(ProviderType.OPENROUTER, OpenRouterProvider)

        tool = DesignChangeTool()
        result = await tool.execute(
            {
                "change_request": (
                    "Add a compact alert card immediately after the hero section. "
                    "Keep it additive and avoid rewriting the whole file unless fragment mode is unsafe."
                ),
                "target_files": [str(tsx_file), str(css_file)],
                "mode": "consensus",
                "output_format": "fragment",
                "model": "flash",
                "models": [
                    {"model": "flash", "stance": "neutral"},
                    {"model": "mistral", "stance": "against"},
                ],
            }
        )

    assert result and result[0].type == "text"
    payload = json.loads(result[0].text)
    assert payload["status"] in {"success", "continuation_available"}
    assert payload["metadata"]["consensus_mode"] is True

    inner = json.loads(payload["content"])
    assert inner["implementation_kind"] == "react_ts"

    if inner["status"] == "cannot_apply_safely":
        assert inner["recommended_output_format"] in {None, "full_files", "fragment"}
        assert inner["reason"]
    elif inner["patch_format"] == "fragment_patch":
        assert inner["operations"]
        files_touched = {op["file"] for op in inner["operations"]}
        assert files_touched.issubset({str(tsx_file), str(css_file)})
    else:
        # Allow a full-file fallback if the formatter determines fragment mode is too risky.
        assert inner["patch_format"] == "full_file_patch"
        updated_files = {entry["file"] for entry in inner["updated_files"]}
        assert updated_files.issubset({str(tsx_file), str(css_file)})

    ModelProviderRegistry.reset_for_testing()
