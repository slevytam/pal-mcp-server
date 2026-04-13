# Design Change Tool - Structured UI Patch Generation

**Request targeted UI changes against existing TSX/CSS or HTML/CSS/JS implementations and get structured patches back**

The `design_change` tool is built for UI evolution work where you already have files on disk and want PAL to propose a design change in a machine-friendly format. It supports both **single-model** and **consensus** workflows, and can return either:

- a small `fragment_patch`
- a `full_file_patch` with complete updated files

Unlike freeform code generation, this tool is designed so PAL or an outer agent can later apply the result automatically.

## Best Fit

Use `design_change` when you want to:

- add a new card, panel, banner, or section to an existing screen
- restyle an existing component while keeping the current implementation stack
- compare multiple model perspectives before choosing a final UI patch
- generate structured output instead of loose snippets

Supported MVP combinations include:

- `.tsx + .css`
- `.jsx + .css`
- `.html + .css`
- `.html + .css + .js`

## How It Works

1. You provide a `change_request` plus the existing target files.
2. PAL infers the implementation kind, such as `react_ts` or `html_css_js`.
3. In `single` mode, one model produces the final patch.
4. In `consensus` mode, PAL gathers multiple model perspectives and then uses one formatter model to emit the final structured patch.
5. The result is validated into one of three shapes:
   - `fragment_patch`
   - `full_file_patch`
   - `cannot_apply_safely`

## Tool Parameters

- `change_request`: Requested UI/design change to make
- `target_files`: Absolute file paths to the relevant structure/style/behavior files
- `mode`: `single` or `consensus`
- `output_format`: `fragment` or `full_files`
- `model`: Formatter model for single mode, or final formatter model for consensus mode
- `models`: Required for consensus mode; list of models to consult
- `framework_hint`: Optional override such as `react_ts`, `react_js`, `html_css`, `html_css_js`
- `images`: Optional screenshots or mockups
- `continuation_id`: Continue previous discussions

## Output Shapes

### `fragment_patch`

Best for small additive edits:

```json
{
  "status": "success",
  "implementation_kind": "react_ts",
  "patch_format": "fragment_patch",
  "summary": "Adds a compact metrics panel.",
  "operations": [
    {
      "id": "op_insert_panel",
      "file": "/abs/path/Dashboard.tsx",
      "file_role": "structure",
      "kind": "insert",
      "target": {
        "locator_type": "anchor_text",
        "value": "<section className=\"hero\">"
      },
      "position": "after",
      "content": "<section className=\"metrics-panel\">...</section>"
    }
  ]
}
```

### `full_file_patch`

Best for broader UI edits or when fragment insertion is too brittle:

```json
{
  "status": "success",
  "implementation_kind": "html_css_js",
  "patch_format": "full_file_patch",
  "summary": "Adds a right-side info panel.",
  "updated_files": [
    {
      "file": "/abs/path/index.html",
      "file_role": "structure",
      "content": "<!doctype html>..."
    }
  ]
}
```

### `cannot_apply_safely`

Used when the requested change cannot be expressed safely in the chosen format:

```json
{
  "status": "cannot_apply_safely",
  "implementation_kind": "react_ts",
  "reason": "No stable insertion anchor was found.",
  "recommended_output_format": "full_files"
}
```

## Example Prompts

**Single model, fragment output**

```
Use design_change with flash to add a compact alert card below the hero section in Dashboard.tsx and dashboard.css. Return fragment output only.
```

**Single model, full-file output**

```
Use design_change with flash to add a new summary panel to this HTML/CSS/JS dashboard and return updated full files.
```

**Consensus, fragment output**

```
Use design_change in consensus mode. Have flash stay neutral and mistral be critical, then format the final result as a fragment patch that adds a promo card after the hero section.
```

**Consensus, full-file output**

```
Use design_change in consensus mode to redesign the top portion of this dashboard and return a full_file_patch.
```

## Best Practices

- Keep `target_files` minimal and relevant.
- Prefer `fragment` mode for small additive UI changes.
- Prefer `full_files` when the layout needs broader reshaping.
- In consensus mode, use a cheap model for deliberation and a reliable formatter model for the final patch.
- Include screenshots in `images` when visual alignment matters.

## When to Use It

- **Use `design_change`** for: Structured UI patch generation against existing front-end files
- **Use `chat`** for: Open-ended UI brainstorming or rough design discussion
- **Use `consensus`** for: Broader product or technical debates not tied to a patch format
- **Use `clink`** for: External CLI experimentation or alternate model behavior
