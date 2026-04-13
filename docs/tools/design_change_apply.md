# Design Change Apply Tool - Patch Execution and Dry Runs

**Apply or dry-run structured `design_change` patch payloads**

The `design_change_apply` tool is a thin executor for the structured payloads returned by [`design_change`](design_change.md). It exists so PAL can validate or apply patch objects without reparsing freeform code.

This tool is intentionally conservative:

- `full_file_patch` replaces complete file contents
- `fragment_patch` applies exact, deterministic operations only
- `dry_run` lets you validate without writing files

## Tool Parameters

- `patch`: The patch payload returned by `design_change`
- `allowed_files`: Optional allowlist of files the patch may touch
- `dry_run`: Defaults to `true`; when enabled, validates and simulates without writing files
- `continuation_id`: Optional conversation continuation

## Current Behavior

### `full_file_patch`

- validates that touched files are allowed
- compares existing content to the proposed content
- reports which files would change or were changed

### `fragment_patch`

- supports exact `anchor_text` insertion
- supports end-of-file append
- applies operations transactionally
- rejects ambiguous anchors instead of guessing

## Example

```json
{
  "patch": {
    "status": "success",
    "implementation_kind": "react_ts",
    "patch_format": "fragment_patch",
    "summary": "Adds an alert card.",
    "operations": [
      {
        "id": "op_insert_alert",
        "file": "/abs/path/Dashboard.tsx",
        "file_role": "structure",
        "kind": "insert",
        "target": {
          "locator_type": "anchor_text",
          "value": "<section className=\"hero\">"
        },
        "position": "after",
        "content": "<section className=\"alert-card\">...</section>"
      }
    ]
  },
  "allowed_files": ["/abs/path/Dashboard.tsx"],
  "dry_run": true
}
```

## Best Practices

- Keep `dry_run=true` while iterating on prompt quality.
- Use `allowed_files` whenever the caller has a known safe file set.
- Prefer `full_file_patch` when insertion anchors are likely to be unstable.

## When to Use It

- **Use `design_change_apply`** for: Validation, dry-run, or execution of structured design patches
- **Use `design_change`** for: Generating the patches in the first place
