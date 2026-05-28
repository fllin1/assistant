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
```

The runner reads `<data_root>/<series>/config/story_profile.json` when
present, otherwise it falls back to the packaged template at
`automations/ln_voice_over_v2/series/templates/story_profile.default.json`.

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
      "display_name": "Chapter 7",
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
| `chapters[].display_name` | yes | human-readable chapter label. |
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
  "order": 0,
  "text": "Chapter text block.",
  "source_unit_ids": ["unit_000042"],
  "parser_hints": {
    "quote_candidate": false
  }
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `segment_id` | yes | stable `seg_NNNNNN` id. |
| `order` | yes | chapter order. |
| `text` | yes | source text. |
| `source_unit_ids` | yes | prepared text unit ids. |
| `parser_hints` | yes | non-authoritative parser hints. |

Optional `parser_hints` keys emitted by this stage are `quote_candidate`
(always present), `quote_style` (on quote segments, values
`ascii|curly|jp-square|jp-double|single`), `quote_unmatched` (set when a
quote span has no closer), and `needs_review` (on placeholder segments for
OCR-failed pages).

Indexing conventions: `chapter_id` suffixes are 1-indexed (`chapter_01`) while
`ChapterIndexEntry.order` is 0-indexed dense. `segment_id` suffixes are
1-indexed (`seg_000001`) while `Segment.order` is 0-indexed dense.

## Validation

- every `segments_file` resolves;
- segment file `chapter_id` matches the index;
- `segment_id` values are unique per chapter;
- `order` values are unique per chapter;
- `text` is non-empty.

## Implementation Notes

Transform is deterministic and code-only. No LLM, OCR, dialogue attribution, scene detection, or audio/visual work happens here. Re-running transform with byte-identical inputs (the prepared volume plus the resolved `story_profile.json`) MUST produce byte-identical outputs.

### Chapter detection

1. Resolve the active `story_profile.json` (per-series override at `<data_root>/<series>/config/story_profile.json` wins; otherwise the packaged template at `automations/ln_voice_over_v2/series/templates/story_profile.default.json`). Log which file won at `INFO`.
2. Compile `rules.chapter_headings` patterns with `re.IGNORECASE | re.MULTILINE`. The optional `(?P<num>\d+(?:\.\d+)?)` capture enables subchapter detection.
3. Walk `PreparedTextUnit`s in volume order, line by line, and record the first heading match per page.
4. A mid-page heading splits the page text at the line break preceding the match: pre-heading slice stays with the prior chapter, heading + post-heading text starts the new chapter. The same `text_unit_id` therefore contributes to two adjacent segments' `source_unit_ids` when a split occurs — no text is silently relocated.
5. `chapter_id` suffix is 1-indexed (`chapter_01`), `ChapterIndexEntry.order` is 0-indexed dense. Subchapter suffix `_N` is emitted when the heading regex captures a fractional `num` or `rules.subchapters` is `true`.
6. `ChapterIndexEntry.display_name` is the matched heading line, NFC-normalized and trimmed (`Prologue`, `Chapter 7`, `Chapter 7.1`). Heading text is also preserved verbatim in the first narration segment of the new chapter so the narrator speaks it at generation.
7. Fallback when no heading matches anywhere: emit a single `chapter_01` with `display_name = "Chapter 1"`; log a `WARNING`.

### Quote-aware segmentation

1. Skip `text_unit`s whose `text` is empty (illustration-only pages). A unit with `needs_review: true` emits a single placeholder segment with `text = "[needs_review:unit_NNNNNN]"`, `parser_hints = {"quote_candidate": false, "needs_review": true}`, and acts as a hard boundary for narration merging and quote tokenization.
2. A finite-state tokenizer recognizes ASCII `"…"`, curly `“…”` / `‘…’`, and Japanese `「…」` / `『…』` pairs. Single curly opens only after whitespace or paragraph start to avoid treating apostrophes (`it's`) as openers. Glyphs are preserved verbatim — they are structural signals and are not folded to ASCII.
3. The tokenizer emits alternating `NARRATION` runs and `QUOTE` spans. Each `QUOTE` becomes one segment with `parser_hints.quote_candidate: true` and a `quote_style` hint. Each `NARRATION` run (whitespace-trimmed, non-empty) becomes one segment with `parser_hints.quote_candidate: false`.
4. Cross-page narration merging is allowed only when no `QUOTE`, no chapter boundary, and no `needs_review` unit lies between the two pages. The resulting segment's `source_unit_ids` lists every contributing unit in page order.
5. Long narration is NOT split by sentence or word count. Stage 4 (scenes) owns beat sizing. Stage 2 never produces a final `segment_type`; `parser_hints.quote_candidate` is a structural hint that Stage 3 (dialogue) is free to override.
6. Unmatched quote spans (no closer before chapter end, or closer would cross a `needs_review` page) are treated as narration with `parser_hints.quote_unmatched: true`; a `WARNING` is logged.
7. Em-dash dialogue (`— Hello`) is treated as narration. No profile rule for it yet.

### Identifier conventions

- `text_unit_id`: 0-indexed `unit_000000` start (matches `stages/prepare/text_units.py`).
- `chapter_id`: `chapter_XX` or `chapter_XX_N`; suffix is 1-indexed (`chapter_01`).
- `segment_id`: 1-indexed `seg_000001` start, unique per chapter, dense.
- `order` on `ChapterIndexEntry` and `Segment`: 0-indexed dense.

### Validation flow

- **Stage-local** (`stages/transform/validation.py`) checks artifact-internal invariants: id regex matches, dense `order`, non-empty `text`, `segments_file == f"segments/{chapter_id}.json"`, unique `chapter_id`s.
- **Cross-artifact** (`pipeline/validators.py::validate_transform_against_prepared`) checks `series`/`volume` agreement, every `source_unit_id` resolves to a `text_unit_id` in the prepared volume, and the union of `source_unit_ids` covers every non-empty `text_unit_id` (including `needs_review` units; illustration-only pages with empty `text` are exempt).
- Both validators run inside `run_transform` BEFORE any file is written, mirroring `stages/prepare/runner.py`. A validation failure leaves the existing `volume_index.json` and `segments/` untouched.

### Determinism inputs

The output is a pure function of two byte streams: `<volume>/prepared/volume.json` and the resolved `story_profile.json`. Operators who edit a per-series `story_profile.json` (e.g. tightening a chapter regex) should expect `chapter_id`s and `segment_id`s to renumber and any downstream Stage 3+ artifacts referencing them to need reconciliation.

## Design History

This section tracks load-bearing design decisions for the transform stage. Append (do not rewrite) entries as decisions land.

- **2026-05-26 — Stage 2 designed via consensus loop (`.omc/plans/lnvo-v2-transform-stage2.md`).** Architect + Critic v1 returned `ITERATE`; v2 resolved mid-page heading split, `needs_review` placeholder handling, validator-call-before-write, and ruff+pytest verification. v3 incorporated user decisions: (B1) the package-level "stages other than prepare are contract-only" rule was dropped; (Q2) `ChapterIndexEntry.display_name` added as a required field, AND heading text retained in the first segment's narration text for TTS; (Q4) quote glyphs preserved verbatim; (Q5) em-dash dialogue deferred; (Q8) heading-regex defaults moved out of Python into a packaged JSON template under `automations/ln_voice_over_v2/series/templates/story_profile.default.json`, with per-series override at `<data_root>/<series>/config/story_profile.json`. Added the Disambiguation Protocol rule to package `AGENTS.md` (spawn Codex agents to read real volume text when content is ambiguous).
- **2026-05-26 — Slice T0 committed** (`feat/lnvo-v2-transform-t0`, `aa401ef`): AGENTS.md rewrite, packaged template, doc updates listed above. Ruff format + check green.
- **2026-05-27 — v3.1 / v3.2 slice-ordering correction (user-driven).** v3.1 introduced an internal `ChapterSplit` dataclass to keep T1 chapter-detection tests green before a mid-stack contract migration. The user identified this as over-engineering: reordering the slices so the contract migration lands first eliminates the shim entirely. v3.2 makes `ChapterIndexEntry.display_name` slice T1; chapter detection becomes T2 and returns `ChapterIndexEntry` directly. Both Architect and Codex Critic had accepted the prior ordering; neither flagged the simpler fix. Lesson kept in the plan revision history.

