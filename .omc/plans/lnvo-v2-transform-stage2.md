# LNVO v2 — Stage 2 (`transform`) Implementation Plan

Status: **pending approval** (v3 draft, no code written yet)

Revision history:
- v1 — initial draft.
- v2 — addressed Architect + Critic v1 findings (mid-page split, `needs_review` resolution, validator-call-in-runner, ruff+pytest verification, Stability Contract, Q1/Q7 promoted to decided).
- v3 — locks user decisions: drops the stage-contract-only restriction in package AGENTS.md; adds `ChapterIndexEntry.display_name`; keeps quote glyphs; defers em-dash dialogue; moves heading-regex defaults to a packaged series template + per-series `<data_root>/<series>/config/story_profile.json`; adds Disambiguation Protocol (Codex agents read volume text when content is ambiguous).
- v3.1 — slice-ordering polish: introduced an internal `ChapterSplit` dataclass to keep T1 green before the contract change landed. **Superseded by v3.2.**
- v3.2 — over-engineering fix (user-driven): the v3.1 `ChapterSplit` shim existed only because the contract change (`ChapterIndexEntry.display_name`) was scheduled at slice 4. Moving the contract change to slice 1 eliminates the shim entirely. New order: T1 = contract migration, T2 = chapters, T3 = quotes, T4 = segments, T5 = validators, T6 = runner, T7 = docs polish. The chapter detector now returns `ChapterIndexEntry` directly; the only remaining private intermediate is a per-unit text-slice helper that bookkeeps partial-page contributions during mid-page splits (genuinely an internal detail, not a contract shim).

Authoritative references:
- `docs/lnvo/02-transform.md` (Volume Index + Segment File contracts).
- `docs/lnvo/01-prepare.md` (PreparedVolume input).
- `docs/lnvo/00-series-parameters.md` (Story profile shape and `<series>/config/` layout).
- `docs/lnvo/contracts-index.md` (id and path rules).
- `automations/ln_voice_over_v2/stages/transform/contracts.py` (Pydantic models already in place; will gain `display_name`).
- `automations/ln_voice_over_v2/series/contracts.py` (`StoryProfile` already has free-form `rules: dict[str, Any]`).
- `automations/ln_voice_over_v2/AGENTS.md` (stage-boundary rules — will be rewritten by this slice; see "Doc Updates").
- `automations/ln_voice_over_v2/stages/prepare/{runner,text_units,validation}.py` (the slice this plan mirrors).
- Root `AGENTS.md` lines 37–65 (Ruff + pytest verification rules).

---

## RALPLAN-DR Summary

### Principles
1. **Deterministic, code-driven only.** No LLM, OCR, attribution, scene detection, or audio/visual generation in Stage 2.
2. **Contracts are authoritative.** The Pydantic models in `stages/transform/contracts.py` and the doc page in `docs/lnvo/02-transform.md` must agree; nothing else may be invented.
3. **Stage 2 produces structural hints, not semantics.** Use `parser_hints.quote_candidate: bool`; never a final `segment_type`.
4. **Provenance is mandatory.** Every segment cites the contributing `text_unit_id`s in `source_unit_ids`. Heading text is never silently relocated and is always preserved in segment `text`.
5. **No artifact sprawl.** Segment text lives in JSON; do not emit chapter `.txt` files.
6. **No volume content guessing.** When implementation depends on what is actually in a volume's text (heading style, dialogue convention, glyph set), spawn Codex agent(s) to read the real text. See "Disambiguation Protocol" in Doc Updates.

### Decision Drivers
1. **Stage boundary discipline** — `transform` owns chapter splitting + quote-aware segmentation only; dialogue/narration/scene reasoning belongs to Stages 3/4.
2. **Stable IDs across reruns** — `chapter_id`/`segment_id` are deterministic functions of `prepared/volume.json` byte content + the loaded `story_profile.json` byte content. See "Stability Contract" below.
3. **Page-provenance round trip** — concatenating each chapter's segment `text` (in order) must cover every non-empty `text_unit` referenced by `source_unit_ids`.

### Viable Options (recap)

- **Chapter detection** → **(B) profile-driven regex** with a packaged default template at `automations/ln_voice_over_v2/series/templates/story_profile.default.json`. (A) and (C) invalidated as default.
- **Segmentation** → **(X) quote-boundary segmentation**, paired with the Stability Contract. (Y) and (Z) invalidated.

---

## Stability Contract

`chapter_id` and `segment_id` are deterministic functions of:
1. The byte content of `<volume>/prepared/volume.json`.
2. The byte content of the active `story_profile.json` (either `<data_root>/<series>/config/story_profile.json` when present, or the packaged template `automations/ln_voice_over_v2/series/templates/story_profile.default.json` when absent).

Consequences:
- Any change to either input file may renumber segments. Stage 3+ artifacts referencing Stage 2 outputs must be reconciled after such a change.
- Cross-page narration merging is bounded by `needs_review` and chapter boundaries; it never silently spans them.
- Mid-page chapter heading splits the page text deterministically; the contributing `text_unit_id` appears in `source_unit_ids` of both the prior chapter's last segment and the new chapter's first segment.
- Re-running transform with the same two inputs MUST produce byte-identical `volume_index.json` and `segments/*.json` (asserted by `test_runner.py::test_determinism`).

---

## Scope

In:
- New `stages/transform/` modules: `__init__.py`, `runner.py`, `chapters.py`, `segments.py`, `quotes.py`, `validation.py`, `__main__.py` (CLI parity with prepare).
- New `automations/ln_voice_over_v2/series/templates/story_profile.default.json` — packaged default series config (default heading regex set lives here, not in Python).
- Public contract change: add `display_name: str` to `ChapterIndexEntry` in `stages/transform/contracts.py`. Required, non-empty.
- A volume-scoped runner that reads `<volume>/prepared/volume.json`, resolves a `story_profile.json` (per-series override or packaged template fallback), and writes `<volume>/volume_index.json` plus `<volume>/segments/chapter_XX[_N].json`.
- A cross-artifact validator added to `pipeline/validators.py`, **called inside `run_transform` before any file write**.
- Unit + runner tests under `tests/automations/ln_voice_over_v2/stages/transform/`.
- Rewrites to `automations/ln_voice_over_v2/AGENTS.md` (drop the "contract-only" rule; add the Disambiguation Protocol) and updates to the doc pages listed in "Doc Updates".

Out:
- No LLM calls, no dialogue attribution, no narration adaptation, no scene boundaries, no audio/visual outputs.
- No new public contract keys on `Segment` (existing `parser_hints` is already `dict[str, Any]`).
- No external runtime dependencies, no subprocess seams, no network.

---

## Outputs (recap from `docs/lnvo/02-transform.md`)

- `<volume>/volume_index.json` — `VolumeIndex` artifact, `chapters[]` ordered.
- `<volume>/segments/<chapter_id>.json` — `SegmentFile` artifact, one per chapter.

ID conventions (locked):
- `chapter_id`: `chapter_XX` or `chapter_XX_N` (e.g., `chapter_01`, `chapter_07_1`).
- `segment_id`: `seg_NNNNNN`, 1-indexed start (`seg_000001`), unique per chapter.
- `order` on both `ChapterIndexEntry` and `Segment`: 0-indexed dense.
- `text_unit_id`: read what `stages/prepare/text_units.py` emits today — 0-indexed `unit_NNNNNN`.

---

## Series Config Resolution (v3 — replaces v2 inline-defaults design)

1. Stage 2's runner resolves the active story profile in this order:
   1. `<data_root>/<series>/config/story_profile.json` (per-series override; preferred).
   2. `automations/ln_voice_over_v2/series/templates/story_profile.default.json` (packaged template; fallback).
2. Both files share the `StoryProfile` shape defined in `docs/lnvo/00-series-parameters.md`. The contract is unchanged — `rules: dict[str, Any]`.
3. Conventional keys this stage reads from `rules`:
   - `rules.chapter_headings: list[str]` — ordered list of Python regex patterns. First match on a line wins.
   - `rules.subchapters: bool` (optional; default `false`) — when `true`, allow `chapter_XX_N` even without a fractional numeric capture (used when the heading style itself signals subchapters, e.g., `◇`).
4. Packaged-template default content:

   ```json
   {
     "schema_version": 1,
     "profile_id": "default",
     "display_name": "Default Story Profile",
     "rules": {
       "chapter_headings": [
         "^\\s*(?:Prologue|Epilogue|Afterword|Interlude)\\b",
         "^\\s*Chapter\\s+(?P<num>\\d+(?:\\.\\d+)?)\\b",
         "^\\s*第\\s*\\d+\\s*章"
       ],
       "subchapters": false
     }
   }
   ```
5. A per-series override file is created **only when the target series needs different rules** — this is a user/operator action, not Stage 2's responsibility. The runner does not auto-copy the template; it just reads either the override or the packaged default and proceeds.
6. The runner logs at `INFO` which file resolved (override path or packaged template), so a re-run can be replicated.

---

## Chapter Detection Strategy

1. **Input:** ordered `PreparedTextUnit`s (page-level). Each unit's `text` may contain a chapter heading anywhere within it.
2. **Heading source:** the resolved `story_profile.json` (see "Series Config Resolution"). Patterns are compiled at runner start with `re.IGNORECASE | re.MULTILINE`.
3. **Per-page scan.** For each `text_unit` in order, walk the unit's `text` line by line. Record the first heading match on the page and capture:
   - The matched line text (for `display_name`).
   - The byte offset of the match line within the unit's `text`.
   - The captured `num` group if present (for subchapter numbering).
4. **Boundary rule (mid-page split).** When a heading matches at line `L` within a page's text:
   - The slice before the line break preceding `L` (the page text up to but not including line `L`) stays with the **prior** chapter; it becomes (or extends) the prior chapter's last narration segment.
   - Line `L` and everything after start the **new** chapter; the heading line is included verbatim in the new chapter's first narration segment.
   - The same `text_unit_id` appears in `source_unit_ids` of both the prior chapter's tail segment and the new chapter's head segment when a mid-page split occurs.
   - If a page contains multiple heading matches (rare), apply this rule recursively to each.
5. **`display_name` derivation.** For each chapter:
   - Use the matched heading line, NFC-normalized, with leading/trailing whitespace trimmed and trailing punctuation kept intact. Example matches: `"Prologue"`, `"Chapter 7"`, `"Chapter 7.1"`, `"第 1 章"`.
   - For the fallback single-chapter case (no heading anywhere), use `"Chapter 1"`.
6. **Subchapter suffix (`_N`).** Emit `chapter_XX_N` when the heading regex captures a fractional `num` (e.g., `"Chapter 7.1"` → `chapter_07_1`) **or** when `rules.subchapters` is `true` and the same `XX` recurs.
7. **Numbering.** `chapter_id` suffix is 1-indexed (`chapter_01`); `ChapterIndexEntry.order` is 0-indexed dense.
8. **Fallback.** If no heading matches anywhere in the volume, emit a single `chapter_01` with `display_name = "Chapter 1"`; log a `WARNING`.
9. **Heading text is NOT discarded** — it lives in the first narration segment's `text` so the narrator speaks it at generation, AND it surfaces structurally as `ChapterIndexEntry.display_name` for video-overlay use.

---

## Segment Creation Strategy

1. **Per-chapter walk.** Iterate the chapter's `PreparedTextUnit`s in volume `order`.
2. **`needs_review` handling.** A unit with `needs_review: true` emits a **single placeholder segment**:
   - `text = "[needs_review:unit_NNNNNN]"` (non-empty, deterministic).
   - `parser_hints = {"quote_candidate": false, "needs_review": true}`.
   - `source_unit_ids = (<that unit_id>,)`.
   - Acts as a hard segmentation boundary: cross-page narration merging and quote tokenization do not span across this unit.
3. **Quote tokenizer (`stages/transform/quotes.py`).** Stream the chapter's contributing text through a finite-state tokenizer:
   - Recognized opening/closing pairs: ASCII `"…"`, curly `“…”`, single curly `‘…’` (only as opener when preceded by whitespace or paragraph start), Japanese `「…」` and `『…』`.
   - Glyphs are preserved verbatim in segment `text`; they are structural signals, not folded to ASCII.
   - Emit alternating `NARRATION` runs and `QUOTE` spans, each carrying its contributing `text_unit_id`s in order.
4. **Segment emission rules.**
   - `QUOTE` token → one `Segment` with `text = <opening + body + closing>`, `parser_hints = {"quote_candidate": true, "quote_style": "<ascii|curly|jp-square|jp-double|single>"}`.
   - `NARRATION` run (whitespace-trimmed, non-empty) → one `Segment` with `parser_hints = {"quote_candidate": false}`.
   - Whitespace-only runs after trim are dropped.
5. **Narration grouping across pages.** A `NARRATION` token may span consecutive `text_units` only when no `QUOTE`, no chapter boundary, and no `needs_review` boundary lies between them. The resulting segment's `source_unit_ids` lists every contributing unit in page order.
6. **No splitting of long narration.** Stage 4 (scenes) owns beat sizing.
7. **No splitting of dialogue.** Quote text is kept intact.
8. **`segment_id` numbering.** Sequential per chapter starting at `seg_000001`. Reset on chapter change. `order` 0-indexed dense.
9. **Whitespace normalization.** NFC unicode normalization before tokenization. Collapse runs of internal blank lines to a single `\n\n`; strip leading/trailing whitespace; preserve single newlines inside text.

---

## Quote Parsing Edge Cases

| Case | Resolution |
| --- | --- |
| Smart apostrophe inside a word (`it's`) | Single-quote opener requires preceding whitespace/paragraph start; mid-word `'` stays in narration. This heuristic is Stage 2's structural-only line. |
| Nested quotes (`"He said, 'no.'"`) | Outer pair forms the segment; inner pair literal. |
| Unmatched open quote | Treat the run as narration; add `parser_hints.quote_unmatched: true`. Logged `WARNING`. |
| Quote span crosses a page boundary (no `needs_review` between) | One segment; `source_unit_ids` lists both pages. |
| Quote span would cross a `needs_review` page | Close heuristically at the page-A boundary; set `quote_unmatched: true`. |
| Italic emphasis (`*word*`/`_word_`) | Ignored. |
| Multi-paragraph quoted span | One segment; internal blank lines preserved. |
| Em-dash dialogue (`— Hello`) | Treated as narration (no profile rule yet — Q5 deferred). |
| Curly-quote with missing close | Same as ASCII unmatched-open. |
| Heading line inside a quote | Impossible by construction (heading regex anchored at line start runs first). |

---

## Page Provenance

- `Segment.source_unit_ids` lists every `text_unit_id` that contributed at least one character, in page order.
- Mid-page heading splits cause one unit to appear in two adjacent segments. The cross-validator accepts this.
- Validator (§"Validation") requires every `text_unit_id` in `prepared/volume.json` — including `needs_review` units — to appear in some segment's `source_unit_ids`. Illustration-only pages with empty `text` and `needs_review: false` are exempt.
- Heading lines that triggered chapter detection are always preserved in the first narration segment of the new chapter.

---

## Validation

### Stage-local (`stages/transform/validation.py`)
Artifact-internal invariants, mirrors `stages/prepare/validation.py`:
- Pydantic strict parse (already guaranteed by `extra="forbid"`).
- `volume_index.chapters[].chapter_id` unique; `order` 0-indexed dense; no gaps.
- `volume_index.chapters[].segments_file == f"segments/{chapter_id}.json"`.
- `volume_index.chapters[].display_name` non-empty after trim.
- For each `SegmentFile`: `segment_id` matches `seg_NNNNNN`, 1-indexed dense suffix; `order` 0-indexed dense; `text` non-empty after trim.

### Cross-artifact (`pipeline/validators.py`, called inside `run_transform` before any write)
New function `validate_transform_against_prepared(index, segments, prepared) -> None`, mirroring `validate_dialogue_against_segments`:
- Series + volume match across all artifacts.
- Each `SegmentFile.chapter_id` matches the corresponding `VolumeIndex.chapters[i].chapter_id`.
- Every `Segment.source_unit_id` resolves to a `text_unit_id` in `prepared/volume.json`.
- Coverage: union of `source_unit_ids` across all segments ⊇ every `text_unit_id` in `prepared/volume.json`, except illustration-only `text_units` (empty `text`, `needs_review: false`).

### Warning-level
- A chapter contains zero quote candidates.
- Heading fallback fired (single chapter for the whole volume).
- Unmatched-quote heuristic fired on any chapter.
- Any `needs_review` placeholder segment emitted.

---

## Runner + CLI Shape

- `stages/transform/runner.py`:
  - `@dataclass(frozen=True) TransformConfig(series, volume, data_root: Path = paths.DEFAULT_PROJECT_DATA_ROOT, story_profile: ProfileId | None = None, force: bool = False)`.
  - `@dataclass(frozen=True) TransformResult(volume_index_path, volume_index, segments_dir, chapter_count, segment_count, needs_review_segment_count, story_profile_source: Path)`.
  - `run_transform(config: TransformConfig) -> TransformResult`:
    1. Load `prepared/volume.json` via `load_json_contract(prepared_volume_path, PreparedVolume)`.
    2. Resolve `story_profile.json` per "Series Config Resolution"; record which file won in `TransformResult.story_profile_source`; log at `INFO`.
    3. Compile heading regex set from `story_profile.rules.chapter_headings`.
    4. Build chapter splits (`chapters.detect_chapters(prepared, headings)`).
    5. Build segments per chapter (`segments.build_segments(prepared, chapter_splits)`).
    6. Construct `VolumeIndex` (with `display_name` per entry) and `SegmentFile` Pydantic models.
    7. Run stage-local `validation.validate_transform_artifacts(index, segments)`.
    8. Run cross-validator `pipeline.validators.validate_transform_against_prepared(index, segments, prepared)` — **before any write**.
    9. If `config.force`: `shutil.rmtree(segments_dir, ignore_errors=True)` and `volume_index_path.unlink(missing_ok=True)`.
    10. `save_json_contract(volume_index_path, index)`; for each `SegmentFile`, `save_json_contract(segment_file_path(...), segment_file)`.
  - No `Callable` seam kwargs. No network. No subprocess.
- `stages/transform/__main__.py`: argparse wrapper with `--series`, `--volume`, `--data-root`, `--story-profile`, `--force`. Mirrors `stages/prepare/__main__.py`.

---

## Contract Change Diff

`automations/ln_voice_over_v2/stages/transform/contracts.py` — add one required field:

```python
class ChapterIndexEntry(ContractModel):
    chapter_id: ChapterId
    order: int = Field(ge=0)
    segments_file: ArtifactPath
    display_name: str = Field(min_length=1)   # NEW
```

`docs/lnvo/02-transform.md` — Volume Index table gains a `display_name` row marked required.

Existing test fixture in `tests/automations/ln_voice_over_v2/test_contracts.py::_volume_index()` will need a `display_name="Chapter 1"` field to keep round-tripping.

---

## Tests

Place under `tests/automations/ln_voice_over_v2/stages/transform/` (mirrors `prepare/`).

### `test_chapters.py`

By the time this slice runs, T1 has already added `display_name` to `ChapterIndexEntry`. The chapter detector returns `ChapterIndexEntry` instances plus a separate, private per-unit slice helper (one entry per contributing `text_unit`, recording the unit id and the text contribution — possibly partial after a mid-page split). That helper is internal to `chapters.py` and feeds T4 segmentation; it is not a public contract.

- Heading at page top → page assigned wholly to new chapter.
- Mid-page heading split → pre-heading text stays with prior chapter; heading + post-heading text starts new chapter; the shared `text_unit_id` appears in the per-unit-slice helper for both neighbours. Assert exact text and exact `text_unit_id` membership at the helper layer.
- Multiple headings on one page → recursive split.
- No heading anywhere → single `ChapterIndexEntry(chapter_id="chapter_01", order=0, display_name="Chapter 1", segments_file="segments/chapter_01.json")`, WARNING logged.
- Subchapter numbering — `"Chapter 7.1"` → `chapter_id == "chapter_07_1"`, `display_name == "Chapter 7.1"`.
- Prologue + Chapter 1 + Epilogue → three `ChapterIndexEntry`s with `order 0/1/2` and respective `display_name`s.
- Per-series override beats packaged template (write a custom `story_profile.json` to `tmp_path` and assert the override wins).

### `test_quotes.py` (string-in, tokens-out; no contract knowledge)
- ASCII, curly, JP `「」`, JP `『』` tokenization.
- Apostrophe-not-opener (`It's a fine day` → single `NARRATION` token).
- Single-quote-as-opener (`'Hello,' she said.` → `QUOTE`, `NARRATION`).
- Nested quotes — single outer `QUOTE`, inner pair literal.
- Unmatched open → `quote_unmatched=True`.
- Multi-paragraph quote → single `QUOTE` with internal blank line preserved.

### `test_segments.py`
- Cross-page narration merge → one segment with `source_unit_ids == ("unit_000005", "unit_000006")`.
- `needs_review` boundary blocks merge → three segments (A narration, B placeholder, C narration). Assert exact placeholder `text` and `parser_hints`.
- Illustration-only page skipped → no segment, cross-validator clean.
- `segment_id` numbering resets per chapter.
- Exact `parser_hints` payloads for quote vs narration.

### `test_runner.py`
- Happy path on synthetic `prepared/volume.json` with Prologue + Chapter 1 + Epilogue → three `SegmentFile`s, `VolumeIndex` with `display_name`s present. Assert exact file paths under `tmp_path`.
- Cross-validator called before write — patch `pipeline.validators.validate_transform_against_prepared` to raise; assert no `volume_index.json` or `segments/*.json` written.
- `--force` wipes pre-existing `segments/chapter_99.json`.
- Determinism — two runs with identical inputs produce byte-equal output files.
- Series config resolution — when `<data_root>/<series>/config/story_profile.json` exists, it wins over the packaged template; assert `TransformResult.story_profile_source` reflects the chosen file.
- CLI smoke via `python -m automations.ln_voice_over_v2.stages.transform`.

### `tests/automations/ln_voice_over_v2/test_validators.py` — extensions
- `validate_transform_against_prepared` happy path.
- Unknown `source_unit_id` → `missing_text_unit`.
- Missing coverage (non-empty, non-`needs_review` unit absent from every `source_unit_ids`) → `missing_coverage`.
- Duplicate `order` within a chapter → `duplicate_order`.
- Gapped `order` (skips 1) → `nonconsecutive_order`.
- Bad `segments_file` path (not matching `segments/<chapter_id>.json`) → `bad_segments_file`.

### Verification command
```
ruff format --check .
ruff check .
pytest tests/automations/ln_voice_over_v2/
```
All three must pass before the slice is reported done.

---

## Doc Updates

All listed below are within scope of Stage 2 slices:

1. **`automations/ln_voice_over_v2/AGENTS.md` — REWRITE (user-approved).**
   - Remove the "Stages other than `stages/prepare/` remain contract-only" rule. Every stage is allowed whatever modules, runner, CLI, or pure-function helpers it needs to deliver its contract.
   - Keep the rule that public contract keys, enum values, artifact paths, and stage names require user confirmation before changing.
   - **Add a "Disambiguation Protocol" section:** when implementation depends on volume-specific content that is not captured in `story_profile.json` or other config (heading style, dialogue convention, glyph set, character names, etc.), spawn one or more Codex agents to read `<data_root>/<series>/<volume>/prepared/volume.json` or `source/` excerpts. Agents must surface findings with concrete page references before code is written. No guessing.
   - **Add a "Series Config" section** documenting that `<data_root>/<series>/config/story_profile.json` is the per-series override location and the packaged template `automations/ln_voice_over_v2/series/templates/story_profile.default.json` is the fallback.

2. **`docs/lnvo/02-transform.md`:**
   - Replace `parser_hints` example `quote_like: false` with `quote_candidate: false`.
   - Document optional `parser_hints` keys this stage emits: `quote_candidate`, `quote_style`, `quote_unmatched`, `needs_review`.
   - Add `display_name` (required, non-empty) to the Volume Index table.
   - Note the `chapter_id` ↔ `order` indexing convention and `seg_NNNNNN` 1-indexed start.
   - Add a short paragraph naming the inputs: `<volume>/prepared/volume.json` (always) and either `<data_root>/<series>/config/story_profile.json` or the packaged default template.

3. **`docs/lnvo/00-series-parameters.md`:**
   - Add a short paragraph under "Story Profile" naming the conventional `rules` keys this stage reads: `chapter_headings: list[str]`, `subchapters: bool`.
   - Reference the packaged template path.

4. **`docs/lnvo/contracts-index.md`:**
   - Clarify that the `seg_NNNNNN` suffix range begins at `seg_000001` (the regex shows the *pattern*, not the starting value).

5. **`automations/ln_voice_over_v2/README.md`:**
   - Add a brief Transform stage section describing the CLI flags and re-run semantics (parallel to the existing Prepare section).

6. **Repository asset:**
   - New file `automations/ln_voice_over_v2/series/templates/story_profile.default.json` with the default heading regex set (see "Series Config Resolution" §4).

---

## Implementation Slices (v3.2 ordering, after approval)

0. **Slice T0 — AGENTS.md rewrite + packaged template + docs prep.** *(DONE, branch `feat/lnvo-v2-transform-t0`, commit `aa401ef`.)*
   - Edited `automations/ln_voice_over_v2/AGENTS.md` (dropped contract-only rule, added Disambiguation Protocol, added Series Config section).
   - Added `automations/ln_voice_over_v2/series/templates/story_profile.default.json`.
   - Updated `docs/lnvo/02-transform.md` and `docs/lnvo/00-series-parameters.md`.

1. **Slice T1 — `ChapterIndexEntry.display_name` contract migration.** Tiny mechanical commit that lands the new required field plus the only existing fixture that constructs the model. Files:
   - `automations/ln_voice_over_v2/stages/transform/contracts.py` — add `display_name: str = Field(min_length=1)` to `ChapterIndexEntry`.
   - `tests/automations/ln_voice_over_v2/test_contracts.py` — update the `_volume_index()` fixture at line 241 to include `display_name="Chapter 1"` so the existing round-trip test keeps passing.

2. **Slice T2 — chapter detection + tests.** Pure functions; reads `StoryProfile`; emits `ChapterIndexEntry` directly (now safe since T1 has landed) plus a private per-unit text-slice helper for partial-page bookkeeping. (`chapters.py`, `test_chapters.py`.)

3. **Slice T3 — quote tokenizer + tests.** Pure function over a string; no contract knowledge. (`quotes.py`, `test_quotes.py`.)

4. **Slice T4 — segmentation + provenance + tests.** Wires T2+T3 into `Segment` emission; handles `needs_review` placeholders and cross-page narration merging. (`segments.py`, `test_segments.py`.)

5. **Slice T5 — stage-local + cross-artifact validators + tests.** Files:
   - `automations/ln_voice_over_v2/stages/transform/validation.py` (stage-local invariants).
   - `automations/ln_voice_over_v2/pipeline/validators.py` (cross-validator `validate_transform_against_prepared`).
   - `tests/automations/ln_voice_over_v2/test_validators.py` (extends with new cross-validator cases).

6. **Slice T6 — runner + CLI + e2e tests.** (`runner.py`, `__main__.py`, `test_runner.py`.) Runner calls stage-local validator then cross-validator before any file write.

7. **Slice T7 — README + `contracts-index.md` polish.**

Each slice is a separately reviewable Codex task with bounded files. Every slice's commit must leave `ruff format --check .`, `ruff check .`, and `pytest tests/automations/ln_voice_over_v2/` all green.

---

## Disambiguation Protocol (Codex agent rule)

Whenever a planning or implementation step needs to know something about the actual content of a volume — examples below — spawn Codex agent(s) to read the real text first:

- Does this LN edition use em-dash dialogue or quote glyphs?
- What heading style does it use? Is `Chapter 7` literal or `◇ 7話`?
- Do chapter headings appear at the top of a recto, or anywhere on a page?
- Are there illustrations that contain readable text?
- Do quoted spans nest? Do they cross paragraphs?

Agents must:
- Read from `<data_root>/<series>/<volume>/prepared/volume.json` or `source/` excerpts, not guess.
- Report findings with concrete `text_unit_id`s or page numbers.
- Multiple agents may be spawned in parallel to sample different parts of a volume; for multi-volume series, sample multiple volumes.

This rule is added to package `AGENTS.md` in Slice T0 so it applies to all future LNVO v2 work, not just Stage 2.

---

## ADR

- **Decision:** Implement Stage 2 as a deterministic, code-only transformer with config-driven chapter detection, quote-aware segmentation that preserves heading text in narration, `needs_review`-safe placeholder segments, and a cross-validator called inside the runner before writes. Drop the package's stage-contract-only rule. Add a Disambiguation Protocol rule. Ship a packaged default series template.
- **Drivers:** Stage-boundary discipline; deterministic ID stability; page-provenance round trip.
- **Alternatives considered:** sentence- and paragraph-level segmentation (rejected — over-fragments / loses dialogue structure); manual chapter map (deferred as future override); whole-page reassignment on mid-page headings (rejected — silent migration); skipping `needs_review` units (rejected — coverage conflict); inline-in-`chapters.py` heading defaults (rejected — series authors won't discover them); hardcoded-in-`series/contracts.py` factory (rejected — layering smell). Config-driven via packaged template + per-series override is the chosen path.
- **Locked decisions:**
  - `text_unit_id` 0-indexed; `segment_id` 1-indexed; `order` 0-indexed dense.
  - `needs_review` units get a non-empty placeholder segment; coverage is a hard validator requirement.
  - Cross-validator runs inside `run_transform` before any file write.
  - `ChapterIndexEntry.display_name: str` required, non-empty.
  - Quote glyphs (curly, JP) are preserved verbatim — not folded to ASCII.
  - Heading text is duplicated: spoken (in first narration segment of the new chapter) AND structural (`display_name` on the index entry).
  - Em-dash dialogue is treated as narration; no profile rule yet.
  - Default chapter-heading regex set lives in the packaged template `automations/ln_voice_over_v2/series/templates/story_profile.default.json`. No inline Python defaults.
  - Stage-contract-only rule in `automations/ln_voice_over_v2/AGENTS.md` is removed in slice T0.
  - Disambiguation Protocol is added in slice T0 and applies to all future LNVO v2 work.
- **Consequences:**
  - Stage 3 must treat `quote_candidate: true` as a candidate only and run its own confirmation.
  - Stage 3 must route `needs_review` placeholder segments to human review.
  - Stage 4 still owns long-narration splitting.
  - Stage 5 (generation) gets `ChapterIndexEntry.display_name` for video-overlay use; the narrator also speaks the heading because it stays in the first segment's narration text.
  - Operators bootstrapping a new series do not need to copy the template — the runner falls back to it transparently — but may copy and edit `<data_root>/<series>/config/story_profile.json` when overrides are needed.
- **Follow-ups:** none open. All v1/v2 blockers and questions are resolved.

---

*This plan is `pending approval` at revision **v3.2**. Slice T0 has been executed and committed on branch `feat/lnvo-v2-transform-t0` (`aa401ef`). No further code, contracts, or test files have been modified. Architect v1: ITERATE → addressed in v2. Critic v1: ITERATE → addressed in v2. v3 incorporated user decisions (B1, Q2, Q4, Q5, Q8) and added the Disambiguation Protocol. Architect v3: APPROVE. Critic v3: ITERATE — two slice-ordering polishes; v3.1 attempted a `ChapterSplit` shim that the user (correctly) rejected as over-engineered. v3.2 fixes the root cause by reordering: contract migration is now slice T1, eliminating the shim entirely.*
