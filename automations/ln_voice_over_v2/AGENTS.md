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

## Boundaries

- This slice owns contracts, validation, path conventions, and orchestration data.
- Runtime series and volume data lives outside the repository.
- Stages other than `stages/prepare/` remain contract-only. Do not add CLI
  commands, OCR, parsing algorithms, LLM prompts, TTS rendering, visual
  rendering, data-porting logic, or plugin frameworks in `stages/transform/`,
  `stages/dialogue/`, `stages/scenes/`, `stages/generation/`, or anywhere
  under `common/`, `pipeline/`, or `series/`.
- `stages/prepare/` may add a runner, a `python -m`-style CLI, PDF
  rasterization, one OCR prompt string, and plain module-level seam
  functions (`run_codex_ocr`, `download_anyflip`) that subprocess external
  CLIs. These seams are kept as free functions injected via `Callable`
  keywords, **not** as Protocols/ports/adapters, so the "Code Rules" bullet
  on empty ports remains satisfied. New external runtime dependencies must
  be installable via PyPI (e.g. `pymupdf`) or documented in the package
  README (e.g. `anyflip-downloader`, `codex`). No vendoring.
- Public contract keys, enum values, artifact paths, and stage names require
  user confirmation before changing.

## Code Rules

- Use Pydantic models with `extra="forbid"` for public contracts.
- Keep modules small and purpose-named.
- Add validators only for contract checks Pydantic cannot express locally.
- Do not add empty runners, ports, adapters, or services until a later slice
  has real orchestration or external-boundary behavior to represent.
