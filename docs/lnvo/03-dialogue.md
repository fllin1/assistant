Dialogue detects spoken dialogue, assigns speakers, and resolves chapter perspective.

## Purpose

| Output | Contract |
| --- | --- |
| Dialogue chapter | `<volume>/dialogue/chapter_XX[_M].json` stores dialogue rows, rejected candidates, perspective, and review state. |

Sufficient handoff: Scenes can treat accepted dialogue rows as spoken beats and remaining segments as narration candidates.

## Inputs

```text
<volume>/volume_index.json
<volume>/segments/chapter_XX[_M].json
<series>/config/characters.json
<series>/config/story_profile.json
```

## Dialogue Chapter

```json
{
  "schema_version": 1,
  "artifact_kind": "dialogue_chapter",
  "series": "classroom-of-the-elite-year-2",
  "volume": "v4",
  "chapter_id": "chapter_07_1",
  "status": "accepted",
  "review_required": false,
  "perspective": {
    "status": "detected",
    "narrator": "Ayanokouji Kiyotaka"
  },
  "dialogues": [
    {
      "segment_id": "seg_000012",
      "speaker": "Horikita Suzune"
    }
  ],
  "rejected_candidates": [
    {
      "segment_id": "seg_000018",
      "reason": "Quoted narration, not spoken dialogue."
    }
  ],
  "review_notes": []
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `artifact_kind` | yes | `dialogue_chapter`. |
| `status` | yes | `accepted` or `needs_review`. |
| `review_required` | yes | review gate flag. |
| `perspective.status` | yes | `unset` or `detected`. |
| `perspective.narrator` | yes | canonical character name or `null`. |
| `dialogues` | yes | accepted or proposed spoken dialogue rows. |
| `dialogues[].segment_id` | yes | referenced segment id. |
| `dialogues[].speaker` | yes | canonical character name or `Unknown`. |
| `rejected_candidates` | yes | quote-like segments rejected as dialogue. |
| `review_notes` | yes | concise review notes. |

Review edits update this file directly until `status: accepted`.

## Validation

- every referenced `segment_id` resolves;
- each segment appears at most once in `dialogues`;
- every speaker is canonical or `Unknown`;
- detected `perspective.narrator` is canonical or `null`;
- downstream stages require `status: accepted`.
