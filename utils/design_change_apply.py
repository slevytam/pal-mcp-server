from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.design_change_models import FragmentPatchResponse, FullFilePatchResponse, PatchOperation


def apply_full_file_patch(
    patch: FullFilePatchResponse,
    allowed_files: set[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply a validated full-file patch conservatively."""

    original_contents: dict[str, str] = {}
    changed_files: list[str] = []
    unchanged_files: list[str] = []

    for updated in patch.updated_files:
        _validate_allowed_file(updated.file, allowed_files)
        path = Path(updated.file)
        original = path.read_text(encoding="utf-8")
        original_contents[updated.file] = original
        if original == updated.content:
            unchanged_files.append(updated.file)
        else:
            changed_files.append(updated.file)

    if dry_run:
        return {
            "status": "dry_run",
            "patch_format": patch.patch_format,
            "would_modify_files": changed_files,
            "unchanged_files": unchanged_files,
        }

    for updated in patch.updated_files:
        if updated.file in changed_files:
            Path(updated.file).write_text(updated.content, encoding="utf-8")

    return {
        "status": "applied",
        "patch_format": patch.patch_format,
        "applied_files": changed_files,
        "unchanged_files": unchanged_files,
        "failed_files": [],
    }


def apply_fragment_patch(
    patch: FragmentPatchResponse,
    allowed_files: set[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply a validated fragment patch transactionally."""

    touched_files = {operation.file for operation in patch.operations}
    original_contents: dict[str, str] = {}
    updated_contents: dict[str, str] = {}
    operation_results: list[dict[str, Any]] = []

    for file_path in touched_files:
        _validate_allowed_file(file_path, allowed_files)
        content = Path(file_path).read_text(encoding="utf-8")
        original_contents[file_path] = content
        updated_contents[file_path] = content

    for operation in patch.operations:
        current = updated_contents[operation.file]
        updated_contents[operation.file] = _apply_operation(current, operation)
        operation_results.append({"id": operation.id, "status": "ok", "file": operation.file})

    changed_files = [
        file_path
        for file_path in touched_files
        if updated_contents[file_path] != original_contents[file_path]
    ]

    if dry_run:
        return {
            "status": "dry_run",
            "patch_format": patch.patch_format,
            "would_modify_files": sorted(changed_files),
            "operation_results": operation_results,
        }

    for file_path in changed_files:
        Path(file_path).write_text(updated_contents[file_path], encoding="utf-8")

    return {
        "status": "applied",
        "patch_format": patch.patch_format,
        "applied_files": sorted(changed_files),
        "operation_results": operation_results,
        "failed_files": [],
    }


def _validate_allowed_file(file_path: str, allowed_files: set[str] | None) -> None:
    if allowed_files is not None and file_path not in allowed_files:
        raise ValueError(f"Patch attempted to modify non-target file: {file_path}")


def _apply_operation(content: str, operation: PatchOperation) -> str:
    if operation.kind == "append":
        return _apply_append(content, operation.content)
    if operation.kind == "insert":
        return _apply_insert(content, operation)
    if operation.kind == "replace":
        return _apply_replace(content, operation)
    raise ValueError(f"Unsupported patch operation kind: {operation.kind}")


def _apply_append(content: str, addition: str) -> str:
    if not content:
        return _normalize_newline(addition)

    separator = "" if content.endswith("\n") else "\n"
    return f"{content}{separator}{_normalize_newline(addition)}"


def _apply_insert(content: str, operation: PatchOperation) -> str:
    anchor = _extract_anchor(operation)
    count = content.count(anchor)
    if count != 1:
        raise ValueError(
            f"Operation {operation.id} could not be applied safely: anchor match count was {count} for {anchor!r}"
        )

    index = content.index(anchor)
    insertion = _normalize_newline(operation.content)
    if operation.position == "before":
        return f"{content[:index]}{insertion}{content[index:]}"
    if operation.position == "after":
        anchor_end = index + len(anchor)
        return f"{content[:anchor_end]}{insertion}{content[anchor_end:]}"
    raise ValueError(f"Insert operation {operation.id} must use before/after, got {operation.position!r}")


def _apply_replace(content: str, operation: PatchOperation) -> str:
    anchor = _extract_anchor(operation)
    count = content.count(anchor)
    if count != 1:
        raise ValueError(
            f"Operation {operation.id} could not be applied safely: anchor match count was {count} for {anchor!r}"
        )
    return content.replace(anchor, _normalize_newline(operation.content), 1)


def _extract_anchor(operation: PatchOperation) -> str:
    if operation.target is None or operation.target.locator_type != "anchor_text" or operation.target.value is None:
        raise ValueError(f"Operation {operation.id} requires an anchor_text target")
    return operation.target.value


def _normalize_newline(value: str) -> str:
    return value if value.endswith("\n") else f"{value}\n"
