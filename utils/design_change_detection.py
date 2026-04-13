from __future__ import annotations

from pathlib import Path

from utils.design_change_models import ImplementationKind

STRUCTURE_EXTENSIONS = {".tsx", ".jsx", ".html"}
STYLE_EXTENSIONS = {".css", ".scss", ".sass", ".less"}
BEHAVIOR_EXTENSIONS = {".js", ".ts"}


def classify_file_role(path: str) -> str:
    """Classify a UI file into structure, style, behavior, or other."""

    ext = Path(path).suffix.lower()
    if ext in STRUCTURE_EXTENSIONS:
        return "structure"
    if ext in STYLE_EXTENSIONS:
        return "style"
    if ext in BEHAVIOR_EXTENSIONS:
        return "behavior"
    return "other"


def infer_implementation_kind(paths: list[str], framework_hint: str | None = None) -> ImplementationKind:
    """Infer the UI implementation kind from the provided file extensions."""

    if framework_hint and framework_hint != "auto":
        mapping: dict[str, ImplementationKind] = {
            "react_ts": "react_ts",
            "react_js": "react_js",
            "html_css": "html_css",
            "html_css_js": "html_css_js",
            "html_css_ts": "html_css_ts",
        }
        return mapping.get(framework_hint, "unknown")

    exts = {Path(path).suffix.lower() for path in paths}

    if ".tsx" in exts:
        return "react_ts"
    if ".jsx" in exts:
        return "react_js"
    if ".html" in exts and ".js" in exts:
        return "html_css_js"
    if ".html" in exts and ".ts" in exts:
        return "html_css_ts"
    if ".html" in exts:
        return "html_css"

    return "unknown"


def group_target_files(paths: list[str]) -> dict[str, list[str]]:
    """Group target files by their inferred role."""

    grouped = {
        "structure": [],
        "style": [],
        "behavior": [],
        "other": [],
    }
    for path in paths:
        grouped[classify_file_role(path)].append(path)
    return grouped
