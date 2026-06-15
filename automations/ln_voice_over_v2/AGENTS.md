# LN Voice Over V2 - Codex Rules

These rules apply to `automations/ln_voice_over_v2/` and
`tests/automations/ln_voice_over_v2/`.

## Scope

This package defines the standalone contract skeleton for LN Voice Over.
The canonical pipeline is:

```text
prepare -> transform -> dialogue -> scenes -> generation
```

Use only this package's stage vocabulary in public contracts.

This sub-project is self-contained. Follow the root rule files, this file, and
the local context/reference files this file names; ignore conventions from
sibling automations or unrelated repo docs.

Branch names for this package must describe the LNVO v2 feature or fix scope,
such as `feat/lnvo-v2-dialogue` or `fix/lnvo-v2-transform`. Do not use
agent/tool prefixes such as `codex/...` or `claude/...`.

## Boundaries

- This slice owns contracts, validation, path conventions, and orchestration data.
- Runtime series and volume data lives outside the repository.
- Every stage may add whatever modules, runner, CLI, or pure-function helpers
  it needs to deliver its contract. External runtime dependencies must be
  installable via PyPI or documented in the package README. No vendoring.
- Public contract keys, enum values, artifact paths, and stage names require
  user confirmation before changing.

## Series Config

Per-series overrides live at `<data_root>/<series>/config/story_profile.json`.
The packaged fallback template is
`automations/ln_voice_over_v2/series/templates/story_profile.default.json`.
The runner reads the override when present, otherwise the template; it does not
auto-copy the template.

## Disambiguation Protocol

When implementation depends on volume-specific content not captured in
`story_profile.json` or other config, such as heading style, dialogue
conventions, glyph sets, or character names, spawn one or more Codex agents to
read `<data_root>/<series>/<volume>/prepared/volume.json` or `source/`
excerpts. Agents report findings with concrete `text_unit_id`s or page
numbers. Multiple parallel agents are allowed, and multi-volume sampling is
expected for multi-volume series. Do not guess about volume content.

## Code Rules

- Use Pydantic models with `extra="forbid"` for public contracts.
- Keep modules small and purpose-named.
- Add validators only for contract checks Pydantic cannot express locally.
- Do not add empty runners, ports, adapters, or services until a later slice
  has real orchestration or external-boundary behavior to represent.
