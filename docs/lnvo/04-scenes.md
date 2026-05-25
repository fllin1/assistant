Scenes turn accepted dialogue and source segments into accepted render beats.

This stage owns scene boundaries, narration adaptation, beat construction, and visual assignment.

## Purpose

| Output | Contract |
| --- | --- |
| Scene draft | `<volume>/scenes/draft/chapter_XX[_M].json` stores generated scenes needing review or acceptance. |
| Scene final | `<volume>/scenes/final/chapter_XX[_M].json` stores the accepted render plan. |

Sufficient handoff: Generation can render audio and visual support from `scenes/final/`.

## Inputs

```text
<volume>/volume_index.json
<volume>/segments/chapter_XX[_M].json
<volume>/dialogue/chapter_XX[_M].json
<series>/config/characters.json
<series>/config/narration_profile.json
<series>/config/visual_profile.json
```

## Internal Passes

| Pass | Contract |
| --- | --- |
| Scene segmentation | group ordered `segment_id` values into scenes. |
| Narration adaptation | condense non-dialogue spans into spoken, silent, omitted, header, or note beats. |
| Beat construction | interleave accepted dialogue and adapted narration. |
| Visual assignment | attach setting, background, visible characters, bubbles, and visual actions. |

## Scene Document

```json
{
  "schema_version": 1,
  "artifact_kind": "scenes_final",
  "series": "classroom-of-the-elite-year-2",
  "volume": "v4",
  "chapter_id": "chapter_07_1",
  "status": "accepted",
  "review_required": false,
  "scenes": []
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `artifact_kind` | yes | `scenes_draft` or `scenes_final`. |
| `status` | yes | `accepted` or `needs_review`. |
| `review_required` | yes | review gate flag. |
| `scenes` | yes | ordered scene list. |

## Scene

```json
{
  "scene_id": "scene_0001",
  "segment_ids": ["seg_000001", "seg_000002"],
  "summary": "A hallway conversation turns tense.",
  "setting": {
    "location": "school hallway",
    "time_of_day": "afternoon",
    "mood": "tense"
  },
  "background": {
    "asset_id": "school-hallway-day",
    "prompt": null
  },
  "visible_characters": [
    {
      "name": "Horikita Suzune",
      "image_id": "horikita-serious",
      "position": "left",
      "expression": "serious"
    }
  ],
  "beats": []
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `scene_id` | yes | stable `scene_0000` id. |
| `segment_ids` | yes | source segments covered by the scene. |
| `summary` | yes | concise story summary. |
| `setting` | yes | `location`, `time_of_day`, `mood`. |
| `background` | yes | asset id or generation prompt. |
| `visible_characters` | yes | character image choices. |
| `beats` | yes | ordered render beats. |

## Beat

```json
{
  "beat_id": "beat_0002",
  "beat_type": "dialogue",
  "segment_id": "seg_000002",
  "segment_ids": [],
  "speaker": "Horikita Suzune",
  "spoken_text": "What are you planning?",
  "bubble_text": "What are you planning?",
  "visual_action": "Horikita questions Ayanokouji.",
  "silence_ms": null
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `beat_id` | yes | stable `beat_0000` id. |
| `beat_type` | yes | `dialogue`, `narration`, `silence`, `omitted`, `chapter_header`, or `note`. |
| `segment_id` | dialogue | source dialogue segment. |
| `segment_ids` | non-dialogue source beats | source segments covered by the beat. |
| `speaker` | dialogue | canonical character name or `Unknown`. |
| `spoken_text` | spoken beats | exact spoken text. |
| `bubble_text` | no | visual bubble text. |
| `visual_action` | no | visual instruction. |
| `silence_ms` | silence | pause duration. |

## Validation

- dialogue input has `status: accepted`;
- every scene segment resolves;
- scene segment ranges are ordered and non-overlapping;
- every accepted dialogue row appears in one dialogue beat;
- every non-dialogue segment is covered by a non-dialogue beat;
- spoken beats have non-empty `spoken_text`;
- final scenes require `status: accepted`;
- character, background, and image ids resolve.
