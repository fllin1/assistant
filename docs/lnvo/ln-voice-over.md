LN Voice Over turns a light novel volume into an audio-first, visual-supported media package.

This folder is repo-tracked Markdown intended to be read from Obsidian. It is
the shared reference for LNVO-related sub-projects in the repository.
Package-local `CONTEXT.md` files stay self-contained; this folder carries the
common vocabulary, contracts, and pipeline decisions.

## Pipeline

```text
series parameters
  -> prepare
  -> transform
  -> dialogue
  -> scenes
  -> generation
```

| Stage | Output |
| --- | --- |
| Series Parameters | accepted once-per-series profiles and assets. |
| Prepare | normalized volume source contract. |
| Transform | stable chapter segment artifacts. |
| Dialogue | accepted dialogue rows, rejected candidates, perspective. |
| Scenes | accepted scene boundaries, narration beats, visual choices. |
| Generation | audio, visual timeline, video, render manifests. |

## Contract Rule

Each stage produces one public contract family. Downstream stages read contracts, not earlier raw inputs.

Required contract facts:

| Fact | Contract |
| --- | --- |
| identity | `schema_version`, `artifact_kind`, `series`, `volume`, optional `chapter_id`. |
| path | artifact-relative POSIX path. |
| ids | stable ids for cross-stage references. |
| status | explicit enum when review or execution state matters. |
| validation | missing references fail before downstream work. |

## Core Terms

| Term | Meaning |
| --- | --- |
| Series | Shared story, character, voice, narration, visual, and render configuration. |
| Volume | One light novel volume processed end to end. |
| Chapter | Canonical text unit created by Transform. |
| Segment | Stable chapter text atom referenced by `segment_id`. |
| Dialogue row | Accepted speaker annotation for one `segment_id`. |
| Perspective | Chapter narrator decision: `unset` or `detected`, with character name or `null`. |
| Scene | Ordered group of source segments with setting, visuals, and beats. |
| Beat | Renderable audio/visual unit inside a scene. |
| Voice key | Key used to resolve a speaker to an accepted TTS voice. |

## Artifact Families

| Artifact | Path |
| --- | --- |
| Prepared volume | `<volume>/prepared/volume.json` |
| Volume index | `<volume>/volume_index.json` |
| Segment file | `<volume>/segments/chapter_XX[_M].json` |
| Dialogue chapter | `<volume>/dialogue/chapter_XX[_M].json` |
| Scene draft | `<volume>/scenes/draft/chapter_XX[_M].json` |
| Scene final | `<volume>/scenes/final/chapter_XX[_M].json` |
| Generation manifest | `<volume>/generation/chapter_XX[_M]/manifest.json` |
| Audio manifest | `<volume>/generation/chapter_XX[_M]/audio_manifest.json` |
| Visual timeline | `<volume>/generation/chapter_XX[_M]/timeline.json` |

## Code Links

| Contract area | Code model |
| --- | --- |
| shared ids, enums, artifact base | `automations/ln_voice_over_v2/common/` |
| series parameters | `automations/ln_voice_over_v2/series/contracts.py` |
| pipeline status | `automations/ln_voice_over_v2/pipeline/contracts.py` |
| prepare | `automations/ln_voice_over_v2/stages/prepare/contracts.py` |
| transform | `automations/ln_voice_over_v2/stages/transform/contracts.py` |
| dialogue | `automations/ln_voice_over_v2/stages/dialogue/contracts.py` |
| scenes | `automations/ln_voice_over_v2/stages/scenes/contracts.py` |
| generation | `automations/ln_voice_over_v2/stages/generation/contracts.py` |
