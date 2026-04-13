from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, Field, model_validator

FileRole: TypeAlias = Literal["structure", "style", "behavior"]
PatchKind: TypeAlias = Literal["insert", "append", "replace"]
PatchPosition: TypeAlias = Literal["before", "after", "end"]
LocatorType: TypeAlias = Literal["anchor_text", "end_of_file"]
ImplementationKind: TypeAlias = Literal[
    "react_ts",
    "react_js",
    "html_css",
    "html_css_js",
    "html_css_ts",
    "unknown",
]


class PatchTarget(BaseModel):
    """Location descriptor for fragment patch operations."""

    locator_type: LocatorType
    value: str | None = None

    @model_validator(mode="after")
    def validate_target(self):
        if self.locator_type == "anchor_text" and not self.value:
            raise ValueError("anchor_text targets require a value")
        if self.locator_type == "end_of_file" and self.value is not None:
            raise ValueError("end_of_file targets must not include a value")
        return self


class PatchOperation(BaseModel):
    """Single fragment-patch operation that can be applied later."""

    id: str = Field(..., description="Stable identifier for this patch operation.")
    file: str = Field(..., description="Absolute target file path.")
    file_role: FileRole
    kind: PatchKind
    target: PatchTarget | None = None
    position: PatchPosition
    content: str = Field(..., description="Raw content to apply. No markdown fences.")

    @model_validator(mode="after")
    def validate_operation(self):
        if not self.content.strip():
            raise ValueError("Patch operations must include non-empty content")

        if self.kind in {"insert", "replace"} and self.target is None:
            raise ValueError(f"{self.kind} operations require a target")

        if self.kind == "append":
            if self.position != "end":
                raise ValueError("append operations must use position='end'")
            if self.target is not None and self.target.locator_type != "end_of_file":
                raise ValueError("append operations may only use end_of_file targets")

        return self


class UpdatedFile(BaseModel):
    """Complete file contents for full-file patch mode."""

    file: str = Field(..., description="Absolute target file path.")
    file_role: FileRole
    content: str = Field(..., description="Complete updated file content. No markdown fences.")

    @model_validator(mode="after")
    def validate_updated_file(self):
        if not self.content.strip():
            raise ValueError("Updated file content must be non-empty")
        return self


class FragmentPatchResponse(BaseModel):
    """Successful response for fragment patch generation."""

    status: Literal["success"] = "success"
    implementation_kind: ImplementationKind
    patch_format: Literal["fragment_patch"] = "fragment_patch"
    summary: str
    operations: list[PatchOperation]

    @model_validator(mode="after")
    def validate_response(self):
        if not self.operations:
            raise ValueError("fragment_patch responses must include at least one operation")
        return self


class FullFilePatchResponse(BaseModel):
    """Successful response for full-file patch generation."""

    status: Literal["success"] = "success"
    implementation_kind: ImplementationKind
    patch_format: Literal["full_file_patch"] = "full_file_patch"
    summary: str
    updated_files: list[UpdatedFile]

    @model_validator(mode="after")
    def validate_response(self):
        if not self.updated_files:
            raise ValueError("full_file_patch responses must include at least one updated file")
        return self


class CannotApplySafelyResponse(BaseModel):
    """Structured fallback when a design change cannot be applied safely."""

    status: Literal["cannot_apply_safely"] = "cannot_apply_safely"
    implementation_kind: ImplementationKind
    reason: str
    recommended_output_format: Literal["fragment", "full_files"] | None = None
