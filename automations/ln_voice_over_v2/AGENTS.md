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

## Boundaries

- This slice owns contracts, validation, path conventions, and orchestration data.
- Runtime series and volume data lives outside the repository.
- Do not add CLI commands, OCR, parsing algorithms, LLM prompts, TTS rendering,
  visual rendering, data-porting logic, or plugin frameworks here.
- Public contract keys, enum values, artifact paths, and stage names require
  user confirmation before changing.

## Code Rules

- Use Pydantic models with `extra="forbid"` for public contracts.
- Keep modules small and purpose-named.
- Add validators only for contract checks Pydantic cannot express locally.
- Do not add empty runners, ports, adapters, or services until a later slice
  has real orchestration or external-boundary behavior to represent.
