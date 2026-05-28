Contracts Index maps Obsidian reference pages to code-level contract models.

Use this page as the quick lookup before changing a stage page or a Pydantic contract.

## Shared Rules

| Rule | Contract |
| --- | --- |
| Base artifact | `schema_version`, `artifact_kind`, `series`, `volume`, optional `chapter_id`. |
| Unknown keys | rejected. |
| Paths | relative POSIX paths only. |
| Review status | `accepted`, `needs_review`. |
| Stage status | `pending`, `running`, `complete`, `failed`, `blocked`, `skipped`. |

## Id Rules

| Id | Pattern |
| --- | --- |
| series, volume, profile, asset | `^[a-z0-9][a-z0-9-]*$` |
| chapter | `chapter_XX` or `chapter_XX_N` |
| text unit | `unit_000000` |
| segment | `seg_000001` |
| scene | `scene_0000` |
| beat | `beat_0000` |

Text units start at `unit_000000`; segment ids match the `seg_NNNNNN` pattern but transform starts numbering at `seg_000001`.

## Artifact Map

| Page | Artifact | Code model |
| --- | --- | --- |
| `01-prepare` | `prepared_volume` | `PreparedVolume` |
| `02-transform` | `volume_index` | `VolumeIndex` |
| `02-transform` | `segment_file` | `SegmentFile` |
| `03-dialogue` | `dialogue_chapter` | `DialogueChapter` |
| `04-scenes` | `scenes_draft` | `SceneDocument` |
| `04-scenes` | `scenes_final` | `SceneDocument` |
| `05-generation` | `generation_manifest` | `GenerationManifest` |
| `05-generation` | `audio_manifest` | `AudioManifest` |
| `05-generation` | `visual_timeline` | `VisualTimeline` |

## Code Paths

| Area | Path |
| --- | --- |
| Common contracts | `automations/ln_voice_over_v2/common/` |
| Series contracts | `automations/ln_voice_over_v2/series/contracts.py` |
| Pipeline contracts | `automations/ln_voice_over_v2/pipeline/contracts.py` |
| Stage contracts | `automations/ln_voice_over_v2/stages/*/contracts.py` |
| Validator API | `automations/ln_voice_over_v2/pipeline/validators.py` |
