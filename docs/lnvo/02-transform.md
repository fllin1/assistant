Transform converts a prepared volume into stable chapter segment files.

## Purpose

| Output | Contract |
| --- | --- |
| Volume index | `<volume>/volume_index.json` orders chapter segment files. |
| Segment files | `<volume>/segments/chapter_XX[_M].json` store stable text segments. |

Sufficient handoff: Dialogue and Scenes can reference text through `segment_id`.

## Inputs

```text
<volume>/prepared/volume.json
<series>/config/story_profile.json
```

## Volume Index

```json
{
  "schema_version": 1,
  "artifact_kind": "volume_index",
  "series": "classroom-of-the-elite-year-2",
  "volume": "v4",
  "chapter_id": null,
  "chapters": [
    {
      "chapter_id": "chapter_07_1",
      "order": 7,
      "segments_file": "segments/chapter_07_1.json"
    }
  ]
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `artifact_kind` | yes | `volume_index`. |
| `chapter_id` | yes | `null`. |
| `chapters` | yes | ordered chapter artifact list. |
| `chapters[].chapter_id` | yes | canonical chapter id. |
| `chapters[].order` | yes | volume order. |
| `chapters[].segments_file` | yes | segment file path. |

## Segment File

```json
{
  "schema_version": 1,
  "artifact_kind": "segment_file",
  "series": "classroom-of-the-elite-year-2",
  "volume": "v4",
  "chapter_id": "chapter_07_1",
  "segments": []
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `artifact_kind` | yes | `segment_file`. |
| `chapter_id` | yes | canonical chapter id. |
| `segments` | yes | ordered text segments. |

## Segment

```json
{
  "segment_id": "seg_000001",
  "order": 1,
  "text": "Chapter text block.",
  "source_unit_ids": ["unit_000042"],
  "parser_hints": {
    "quote_like": false
  }
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `segment_id` | yes | stable `seg_000000` id. |
| `order` | yes | chapter order. |
| `text` | yes | source text. |
| `source_unit_ids` | yes | prepared text unit ids. |
| `parser_hints` | yes | non-authoritative parser hints. |

## Validation

- every `segments_file` resolves;
- segment file `chapter_id` matches the index;
- `segment_id` values are unique per chapter;
- `order` values are unique per chapter;
- `text` is non-empty.
