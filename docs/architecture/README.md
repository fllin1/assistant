# Architecture Maps

This directory is the repository-level entry point for architecture and codebase navigation maps. The detailed maps stay close to the code they describe; this hub links them together and tracks the order in which broader coverage should grow.

## Current Maps

| Area | Curated map | Generated facts |
| --- | --- | --- |
| LN Voice-Over automation | [automations/ln_voice_over/docs/architecture.md](../../automations/ln_voice_over/docs/architecture.md) | [imports](../../automations/ln_voice_over/docs/generated/lnvo-imports.mmd), [symbols](../../automations/ln_voice_over/docs/generated/lnvo-symbols.md), [tests](../../automations/ln_voice_over/docs/generated/lnvo-test-map.md) |

## Documentation Model

The long-term shape is mixed:

- Curated Markdown handbooks explain intent, boundaries, data contracts, and module interface cards.
- Generated artifacts capture source-backed facts such as imports, public symbols, paths, line numbers, and test coverage hints.
- AI review compares the curated layer to generated facts and source code, then proposes corrections before humans rely on the map.

Generated files are committed so the repository remains navigable without rerunning tools. They should still be refreshed whenever architecture docs are touched.

## Roadmap

1. Keep polishing LN Voice-Over while the project is small.
2. Add a compact map for `src/assistant/` once the reusable library surface grows beyond a few flat modules.
3. Add cross-automation maps only after more than one automation shares a meaningful pattern.
4. Consider a small documentation site only after the Markdown/Mermaid source of truth starts to feel hard to browse.

## Regeneration

For LN Voice-Over:

```bash
uv run --locked python scripts/generate_architecture_docs.py \
    --source automations/ln_voice_over \
    --tests tests/automations/ln_voice_over \
    --output automations/ln_voice_over/docs/generated \
    --module-prefix automations.ln_voice_over \
    --name lnvo
```
