Prepare converts raw volume material into a normalized prepared volume.

## Purpose

| Output | Contract |
| --- | --- |
| Raw archive | `<volume>/source/` stores reproducible source files. |
| Prepared volume | `<volume>/prepared/volume.json` stores ordered text units and media inventory. |

Sufficient handoff: Transform can read `prepared/volume.json` and build canonical chapter segments.

## Inputs

| Input | Examples |
| --- | --- |
| text | copied web text, manual `.txt`, ebook export. |
| PDF | PDF, page images, page metadata. |
| OCR | OCR text, OCR sidecars, review notes. |
| mixed | merged source material. |

## Prepared Volume

```json
{
  "schema_version": 1,
  "artifact_kind": "prepared_volume",
  "series": "classroom-of-the-elite-year-2",
  "volume": "v4",
  "chapter_id": null,
  "story_profile": "classroom-of-the-elite",
  "source_profile": "pdf-ocr",
  "text_units": [],
  "media": []
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `schema_version` | yes | artifact schema version. |
| `artifact_kind` | yes | `prepared_volume`. |
| `series` | yes | series id. |
| `volume` | yes | volume id. |
| `chapter_id` | yes | `null`. |
| `story_profile` | yes | story profile id. |
| `source_profile` | yes | source adapter/profile id. |
| `text_units` | yes | ordered normalized text blocks. |
| `media` | yes | ordered media inventory. |

## Prepared Text Unit

```json
{
  "text_unit_id": "unit_000042",
  "order": 42,
  "text": "Normalized text block.",
  "source_path": "source/pages/183.png",
  "source_locator": {
    "page": 183
  }
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `text_unit_id` | yes | stable `unit_000000` id. |
| `order` | yes | volume order. |
| `text` | yes | normalized text. |
| `source_path` | yes | source artifact path. |
| `source_locator` | yes | source-local locator object. |

## Prepared Media

```json
{
  "media_id": "illustration-001",
  "order": 1,
  "media_type": "illustration",
  "path": "prepared/media/illustration-001.png",
  "source_path": "source/pages/012.png"
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `media_id` | yes | stable asset id. |
| `order` | yes | media order. |
| `media_type` | yes | `image`, `page_image`, or `illustration`. |
| `path` | yes | prepared media path. |
| `source_path` | yes | source artifact path. |

## Validation

- `text_units` is non-empty;
- `order` values are unique per list;
- artifact paths are relative POSIX paths;
- `story_profile` and `source_profile` resolve.
