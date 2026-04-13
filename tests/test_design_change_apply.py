"""
Tests for the design change apply utilities.
"""

from utils.design_change_apply import apply_fragment_patch, apply_full_file_patch
from utils.design_change_models import (
    FragmentPatchResponse,
    FullFilePatchResponse,
)


class TestDesignChangeApply:
    def test_apply_full_file_patch_dry_run(self, tmp_path):
        html_file = tmp_path / "index.html"
        css_file = tmp_path / "styles.css"
        html_file.write_text("<div>Old</div>\n", encoding="utf-8")
        css_file.write_text(".old { color: red; }\n", encoding="utf-8")

        patch = FullFilePatchResponse.model_validate(
            {
                "status": "success",
                "implementation_kind": "html_css",
                "patch_format": "full_file_patch",
                "summary": "Update both files.",
                "updated_files": [
                    {
                        "file": str(html_file),
                        "file_role": "structure",
                        "content": "<div>New</div>\n",
                    },
                    {
                        "file": str(css_file),
                        "file_role": "style",
                        "content": ".new { color: blue; }\n",
                    },
                ],
            }
        )

        result = apply_full_file_patch(patch, allowed_files={str(html_file), str(css_file)}, dry_run=True)

        assert result["status"] == "dry_run"
        assert sorted(result["would_modify_files"]) == sorted([str(html_file), str(css_file)])
        assert html_file.read_text(encoding="utf-8") == "<div>Old</div>\n"
        assert css_file.read_text(encoding="utf-8") == ".old { color: red; }\n"

    def test_apply_full_file_patch_writes_files(self, tmp_path):
        html_file = tmp_path / "index.html"
        html_file.write_text("<div>Old</div>\n", encoding="utf-8")

        patch = FullFilePatchResponse.model_validate(
            {
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
            }
        )

        result = apply_full_file_patch(patch, allowed_files={str(html_file)}, dry_run=False)

        assert result["status"] == "applied"
        assert result["applied_files"] == [str(html_file)]
        assert html_file.read_text(encoding="utf-8") == "<div>New</div>\n"

    def test_apply_fragment_patch_insert_and_append(self, tmp_path):
        tsx_file = tmp_path / "App.tsx"
        css_file = tmp_path / "app.css"
        tsx_file.write_text(
            "<main>\n<section className=\"hero\">Hero</section>\n</main>\n",
            encoding="utf-8",
        )
        css_file.write_text(".hero { display: block; }\n", encoding="utf-8")

        patch = FragmentPatchResponse.model_validate(
            {
                "status": "success",
                "implementation_kind": "react_ts",
                "patch_format": "fragment_patch",
                "summary": "Add metrics card.",
                "operations": [
                    {
                        "id": "op_insert_card",
                        "file": str(tsx_file),
                        "file_role": "structure",
                        "kind": "insert",
                        "target": {"locator_type": "anchor_text", "value": "<section className=\"hero\">"},
                        "position": "after",
                        "content": "\n<section className=\"metrics-card\">Card</section>",
                    },
                    {
                        "id": "op_append_styles",
                        "file": str(css_file),
                        "file_role": "style",
                        "kind": "append",
                        "target": {"locator_type": "end_of_file"},
                        "position": "end",
                        "content": ".metrics-card { padding: 16px; }",
                    },
                ],
            }
        )

        result = apply_fragment_patch(patch, allowed_files={str(tsx_file), str(css_file)}, dry_run=False)

        assert result["status"] == "applied"
        assert sorted(result["applied_files"]) == sorted([str(tsx_file), str(css_file)])
        assert "metrics-card" in tsx_file.read_text(encoding="utf-8")
        assert ".metrics-card { padding: 16px; }" in css_file.read_text(encoding="utf-8")

    def test_apply_fragment_patch_dry_run_does_not_write(self, tmp_path):
        html_file = tmp_path / "index.html"
        html_file.write_text("<main><section>Hero</section></main>\n", encoding="utf-8")

        patch = FragmentPatchResponse.model_validate(
            {
                "status": "success",
                "implementation_kind": "html_css",
                "patch_format": "fragment_patch",
                "summary": "Insert banner.",
                "operations": [
                    {
                        "id": "op_insert_banner",
                        "file": str(html_file),
                        "file_role": "structure",
                        "kind": "insert",
                        "target": {"locator_type": "anchor_text", "value": "<section>Hero</section>"},
                        "position": "after",
                        "content": "<aside>Banner</aside>",
                    }
                ],
            }
        )

        result = apply_fragment_patch(patch, allowed_files={str(html_file)}, dry_run=True)

        assert result["status"] == "dry_run"
        assert result["would_modify_files"] == [str(html_file)]
        assert html_file.read_text(encoding="utf-8") == "<main><section>Hero</section></main>\n"

    def test_apply_fragment_patch_fails_transactionally_when_anchor_missing(self, tmp_path):
        tsx_file = tmp_path / "App.tsx"
        css_file = tmp_path / "app.css"
        original_tsx = "<main>\n<section className=\"hero\">Hero</section>\n</main>\n"
        original_css = ".hero { display: block; }\n"
        tsx_file.write_text(original_tsx, encoding="utf-8")
        css_file.write_text(original_css, encoding="utf-8")

        patch = FragmentPatchResponse.model_validate(
            {
                "status": "success",
                "implementation_kind": "react_ts",
                "patch_format": "fragment_patch",
                "summary": "Broken patch.",
                "operations": [
                    {
                        "id": "op_insert_card",
                        "file": str(tsx_file),
                        "file_role": "structure",
                        "kind": "insert",
                        "target": {"locator_type": "anchor_text", "value": "<section className=\"missing\">"},
                        "position": "after",
                        "content": "<section className=\"metrics-card\">Card</section>",
                    },
                    {
                        "id": "op_append_styles",
                        "file": str(css_file),
                        "file_role": "style",
                        "kind": "append",
                        "target": {"locator_type": "end_of_file"},
                        "position": "end",
                        "content": ".metrics-card { padding: 16px; }",
                    },
                ],
            }
        )

        try:
            apply_fragment_patch(patch, allowed_files={str(tsx_file), str(css_file)}, dry_run=False)
            assert False, "Expected fragment patch application to fail"
        except ValueError as exc:
            assert "could not be applied safely" in str(exc)

        assert tsx_file.read_text(encoding="utf-8") == original_tsx
        assert css_file.read_text(encoding="utf-8") == original_css
