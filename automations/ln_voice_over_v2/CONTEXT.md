# LN Voice Over V2 Context

This context is self-contained and applies only to
`automations/ln_voice_over_v2/`.

The Obsidian LNVO documentation is the shared reference for pipeline vocabulary,
stage contracts, and cross-project planning notes. This file keeps only the
package-local context needed by agents working in this code tree.

## Pipeline Terms

**Prepare** normalizes raw source material into a prepared volume contract.

**Transform** turns a prepared volume into stable chapter segment artifacts.

**Dialogue** detects spoken dialogue, assigns speakers, records rejected
quote-like candidates, and resolves chapter perspective.

**Scenes** turns accepted dialogue and source segments into scene boundaries,
adapted narration beats, dialogue beats, and visual choices.

**Generation** records audio and visual media output contracts from final scenes.

## Canonical Data

The v2 public data format is JSON backed by strict Pydantic contracts.

Persisted artifacts carry:

- `schema_version`
- `artifact_kind`
- `series`
- `volume`
- optional `chapter_id`

Stage contracts may add only the keys they own.
