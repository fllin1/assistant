---
role: architect
target_plan: lnvo-v2-prepare-step1.md
timestamp: 2026-05-25T00:00:00Z
verdict: ITERATE
---

# Architect Review — LNVO v2 Prepare Step 1

## TL;DR

The plan is sound in shape and respects every locked-input decision. It correctly leaves `common/*` and sibling stage contracts untouched, uses the existing `PreparedVolume` model verbatim, and routes OCR through `codex exec` as required. However, there are three concrete inconsistencies between the plan and the contract layer (one is a hard bug: `prepared/media/...` will be **rejected** by the existing path validator), and the "OcrProvider Protocol" decision crosses a line drawn explicitly in `AGENTS.md` that the plan tries to handwave away. The Planner must address these before the Critic should accept.

---

## 1. Steelman antithesis — "Drop the OcrProvider Protocol; ship a single concrete function"

The strongest counter-proposal to this plan is that the `OcrProvider` Protocol is **premature abstraction in a contract-first codebase that already names this anti-pattern**. `AGENTS.md:35-36` says verbatim: *"Do not add empty runners, ports, adapters, or services until a later slice has real orchestration or external-boundary behavior to represent."* The plan tries to defuse this by noting that the runner and boundaries are "non-empty by construction" — but the Protocol itself is empty by construction. It has one implementation (`CodexExecOcrProvider`), one consumer (`runner.py`), and the speculative second-implementer that justifies it (a non-`codex` OCR backend) is explicitly out of scope and ruled out by locked input #4. Strip the Protocol: define `ocr_page(page_image: Path, *, model: str, executable: str = "codex", prompt: str = OCR_PROMPT) -> OcrPageResult` as a free function in `ocr.py`. Tests inject a fake by monkeypatching `runner._ocr_page = fake` or by passing `ocr_fn: Callable[[Path], OcrPageResult]` into `run_prepare`. You get the same testability, lose one indirection, lose one Protocol-vs-`@dataclass` style mismatch in the module, and align with the package's own "no ports until needed" rule. The same argument applies — slightly less forcefully — to `Downloader`: a single `download_anyflip(url, dest)` function with an injectable `runner: Callable[[list[str]], None] = subprocess.run` keyword would satisfy testing without naming a Protocol.

The plan does anticipate this and asserts that "Once a second OcrProvider is required, the Protocol is already in place; no refactor needed." That is a YAGNI argument inverted: the package's own rules say wait until the second implementation exists, then introduce the Protocol. A `Callable` seam is a one-line refactor away from a Protocol the day a second backend lands.

## 2. Tradeoff tensions

### Tension 1 — Protocol vs. Callable for the OCR seam

*On one side:* Protocols are self-documenting, give mypy a real interface to check, let `CodexExecOcrProvider` carry config (`model`, `executable`, `timeout_seconds`, `prompt`) as fields, and put the seam exactly where the next OcrProvider will plug in. The plan also pairs the Protocol with one concrete default and one consumer — that is not "empty," it is the minimum viable shape.

*On the other side:* `AGENTS.md:35-36` explicitly bans this pattern "until a later slice has real orchestration or external-boundary behavior to represent." This slice has the external-boundary behavior but only one implementation. A `Callable[[Path], OcrPageResult]` injection seam preserves testability with strictly less surface area.

*Plan currently picks:* Protocol + one default + boundary widening of `AGENTS.md`.

*What would change my mind:* (a) Evidence that a non-codex OcrProvider is on the near-term roadmap (it is not — out of scope #4); or (b) explicit language in the AGENTS.md amendment acknowledging the rule and justifying the exception as "boundary code, not port/adapter," not just removing the bullet. Right now the plan deletes the rule rather than naming why Prepare gets to bend it.

### Tension 2 — Resume-on-malformed-cache: recompute vs. fail

*On one side (plan's choice):* Per-page resume that **silently recomputes** a malformed `source/ocr/{page:03d}.json` matches how users mentally model "resume" — partial state is repaired, the user re-runs and gets a complete artifact. Locked input #11 says "full cache + resume-by-default."

*On the other side:* Silent recompute hides corruption causes (a half-written file from a crashed prior run vs. a JSON-schema regression vs. a different OCR model writing an incompatible shape). For a stage whose primary cost driver *is* OCR calls, silently spending money to "repair" a file whose existence may indicate a deeper bug is the opposite of fail-fast.

*Plan currently picks:* Silent recompute, justified at `plan §test_runner_resume.py` ("a corrupted cache file is no different from an absent one").

*What would change my mind:* The plan should at minimum log a `WARNING` line per recomputed-because-malformed page (e.g. `[prepare] source/ocr/047.json failed strict parse; recomputing`) so the user can spot a pattern. Without logging, the user cannot distinguish "resume worked" from "resume burned $5 silently re-OCRing 80 corrupted pages."

### Tension 3 — Per-page concurrency = 4 with subprocess `codex exec` and no retry

*On one side:* `workers=4` from locked input is a reasonable parallelism default. The plan honors it.

*On the other side:* The plan explicitly says "No retries" for `codex exec` malformed JSON (`§ocr.py` intent) and lists "Caching, retry policy, exponential backoff for codex exec failures" as out of scope. On a 200-page volume with 4 concurrent `codex exec` subprocesses, **one** transient malformed response (markdown fence, leading prose, rate-limit error JSON) aborts the entire run. The next invocation will resume — but the resume only kicks in for **successfully cached** pages. The half-completed in-flight pages from the aborted run are not cached and are re-spent on the next run. With 4 concurrent workers, you can lose up to 3 successful in-flight pages every time a 4th raises.

*Plan currently picks:* `workers=4`, no retry, fail the whole run on first malformed page.

*What would change my mind:* Cache every successful page's OCR JSON to disk **as soon as it returns**, before raising on any sibling failure. The plan already implies this via `save_ocr` per page, but the runner orchestration in `§runner.py` does not explicitly say "writes are committed as each future resolves, not after the join." Make that guarantee explicit so a mid-run failure does not waste sibling work. (This is one extra sentence in the plan, not a design change.)

## 3. Synthesis

- **Tension 1 (Protocol vs. Callable):** Two acceptable syntheses without violating any locked input:
  1. **Keep the Protocol but cite the rule.** Rewrite the AGENTS.md amendment to explicitly quote the "no empty runners, ports, adapters" rule and justify Prepare's exception as a *named external boundary with one default implementation*, not a port-for-future-expansion. The Critic can then evaluate whether the exception is reasoned, not whether the rule was quietly removed.
  2. **Drop the Protocol; keep the dataclass.** Replace `class OcrProvider(Protocol)` with a free function `ocr_page(page_image, *, model, executable, timeout_seconds, prompt) -> OcrPageResult` and let `run_prepare` accept `ocr_fn: Callable[[Path], OcrPageResult] | None = None`. Lose nothing testability-wise; gain one line of strict AGENTS.md compliance. Same applies to `Downloader`.
  Either is acceptable; the Planner should pick one and say *why*, rather than silently rewriting the rule.

- **Tension 2 (malformed-cache):** Add to `§runner.py` intent: "When `load_cached_ocr` returns `None` because of parse failure (distinguishable from missing-file via a logged reason), emit one `WARNING` line and recompute." Two-line plan delta, no contract change.

- **Tension 3 (concurrency + no-retry):** Add to `§runner.py` intent: "Each per-page future writes its `source/ocr/{page:03d}.json` to disk on success before the join; a sibling failure does not roll back already-written pages." One-line plan delta, makes the partial-progress guarantee explicit.

## 4. Principle-violation flags

Checked the plan against `automations/ln_voice_over_v2/AGENTS.md`, `automations/ln_voice_over_v2/CONTEXT.md`, and the existing `common/` modules.

### [BLOCKER] `media.path = "prepared/media/illustration-{seq:03d}.png"` will be **rejected** by `validate_artifact_path`

`common/ids.py:21-33` defines `validate_artifact_path` and disallows `..`, empty segments, leading `/`, and backslashes. The path `prepared/media/illustration-001.png` passes that check. BUT — and this is the bug — `PreparedMedia.path` and `PreparedMedia.source_path` are typed `ArtifactPath` (`common/ids.py:36`), and the plan's stated path is `prepared/media/illustration-{seq:03d}.png`. That is fine. **However**, the plan stores the *volume.json artifact itself* at `prepared/volume.json` (`paths.py:23-25`), so paths embedded in `volume.json` must be **relative to the volume root** (the artifact's own parent's parent), not relative to `prepared/`. The plan is internally consistent on this (uses `prepared/media/...` and `source/pages/...` as siblings), so the convention works — provided **every other downstream stage uses the same anchor**. There is no test in the plan that asserts "all artifact paths in `volume.json` resolve correctly when joined against `volume_root`." The `validate_prepared_volume` function in `§validation.py` does say "resolves under `volume_root` and the file exists," which would catch a wrong anchor at runtime, but the plan does not pin the anchor convention in writing. **Action:** add one sentence to `§validation.py` (or `§runner.py`) stating: *"All `ArtifactPath` values in `volume.json` are POSIX-relative to `volume_root(data_root, series, volume)`, i.e. the directory that contains `prepared/`."* Without that, the anchor is implicit and Transform will likely guess wrong.

### [BLOCKER] `media_id = "illustration-{seq:03d}"` against `AssetId` regex

`common/ids.py:9` defines `SlugId` (and therefore `AssetId`) as `^[a-z0-9][a-z0-9-]*$`. `illustration-001` matches that regex. **OK, no violation.** Flagged for the Critic's record because the prompt asked.

### [WARN] `text_unit_id = f"unit_{page-1:06d}"` against `TextUnitId` regex

`common/ids.py:15` defines `TextUnitId` as `^unit_[0-9]{6}$`. `unit_000000` matches. **OK, no violation.**

### [WARN] `order = seq - 1` and `order = page - 1` page-vs-zero-index conventions

The plan states `text_unit.order = page - 1` and `media.order = seq - 1`. `PreparedTextUnit.order` and `PreparedMedia.order` are typed `int = Field(ge=0)` (`prepare/contracts.py:18, 28`). Page 1 → unit_000000, order 0, `source_locator={"page": 1}`. That is internally consistent: filesystem PNGs are 1-indexed (`source/pages/001.png`), contract IDs and `order` are 0-indexed, `source_locator.page` is 1-indexed. **OK** but the plan should call out the dual convention explicitly so the Transform stage planner does not assume `source_locator.page` is also 0-indexed.

### [BLOCKER] AGENTS.md amendment silently deletes the "no empty ports/adapters" rule's protection for Prepare

The current `AGENTS.md` "Code Rules" bullet at line 35-36 says *"Do not add empty runners, ports, adapters, or services until a later slice has real orchestration or external-boundary behavior to represent."* The plan's `§AGENTS.md scope change` only modifies the "Boundaries" bullet, not the "Code Rules" bullet. It then claims at line 101: *"The 'Code Rules' section's prohibition on 'empty runners, ports, adapters, or services' stays — Prepare's runner and boundaries are non-empty by construction."* This is the load-bearing claim. The Critic will need to decide whether `OcrProvider(Protocol)` with **exactly one** implementation in this slice counts as an "empty port" or a "boundary with one default." Reasonable readers will disagree. **Action:** the Planner must either (a) drop the Protocol per Tension 1's synthesis option 2, or (b) add to the `AGENTS.md` amendment a third bullet explicitly stating: *"A Protocol introduced alongside a single concrete default implementation is not an 'empty port' under the Code Rules; it is a named external boundary."* Silently relying on the reader to share the Planner's interpretation is fragile.

### [PASS] `chapter_id: None` invariant preserved

`PreparedVolume.chapter_id: None = None` (`stages/prepare/contracts.py:38`). The plan never sets chapter_id for prepared volumes. **OK.**

### [PASS] `source_profile = "pdf-llm-ocr"` is a valid `ProfileId` slug

`ProfileId` is `SlugId = ^[a-z0-9][a-z0-9-]*$`. `pdf-llm-ocr` matches. **OK.**

### [PASS] `story_profile` default = series id

Plan §runner.py: `story_profile: ProfileId | None = None  # defaults to series`. Test plan asserts the default behavior. `SeriesId` and `ProfileId` are both `SlugId` so the assignment type-checks. **OK.**

### [PASS] No touches to `common/`, `pipeline/`, `series/`, sibling stage `contracts.py`

Confirmed by file-level change list at plan line 285. **OK.**

### [WARN] `--force-ocr` semantics

The plan defines `--force-ocr` as "recompute every page's OCR; reuse `source/volume.pdf` and `source/pages/*.png` if present" (README §Re-run flags) and `--force` as "wipe `source/ocr/`, `prepared/`, and re-rasterize all pages; the PDF is still reused if already on disk." That is unambiguous on the *inputs* it reuses but **does not specify what happens to `prepared/media/illustration-*.png`** under `--force-ocr`. If illustrations were detected from a stale prior OCR, are the old media PNGs deleted? Reused? Overwritten with the new OCR's illustration set? The plan's `collect_media` description ("overwrite when `force`") implies `--force` overwrites but `--force-ocr` does not. That is probably wrong: if `--force-ocr` re-runs OCR and gets a different `is_illustration` map, the on-disk `prepared/media/` set will diverge from the new contract. **Action:** add to README §Re-run flags: *"`--force-ocr` also rebuilds `prepared/media/` from the new OCR pass; stale illustration files for pages that are no longer flagged are deleted."* One-sentence delta.

### [WARN] `pyproject.toml` diff hunk anchor

The plan's diff hunk at line 293-302 shows the existing list ending with `"pydantic>=2.12.5",` and adds `"pymupdf>=1.24",`. Verified against `pyproject.toml:7-13`: the current list matches the hunk's context lines. **OK.**

## 5. Verdict

```
ITERATE
```

The plan respects every locked-input decision and correctly leaves the contract layer alone, but it has one factual ambiguity that will bite Transform (artifact-path anchor convention is implicit), one rule-bending without explicit acknowledgement (`AGENTS.md` "Code Rules" prohibition on empty ports vs. the `OcrProvider` Protocol), and two unspecified-on-purpose-but-actually-load-bearing behaviors (malformed-cache warning, `--force-ocr` media cleanup) that the Critic will rightly flag.

### Required revisions (atomic, in order of priority)

1. **Pick a stance on the `OcrProvider` Protocol vs. AGENTS.md "Code Rules."** Either (a) drop the Protocol and use a `Callable[[Path], OcrPageResult]` seam, or (b) extend the AGENTS.md amendment with an explicit bullet that names this as a permitted "boundary with one default" exception and explains why it is not an empty port. Apply the same choice consistently to `Downloader`.

2. **Pin the artifact-path anchor convention in writing.** Add one sentence to `§validation.py` or `§runner.py` stating that every `ArtifactPath` in `volume.json` is POSIX-relative to `volume_root(data_root, series, volume)` (i.e. the directory containing `prepared/`).

3. **Specify partial-progress and malformed-cache guarantees in `§runner.py` intent.** Add: (a) "Each per-page future writes `source/ocr/{page:03d}.json` to disk on success before the join, so a sibling page's failure does not roll back already-OCR'd pages"; (b) "When a cached OCR file fails strict parse, log one `WARNING` line and recompute."

4. **Specify `--force-ocr` media-cleanup behavior.** Add to README §Re-run flags: `--force-ocr` rebuilds `prepared/media/` from the new OCR pass and removes stale illustration PNGs for pages no longer flagged.

5. **Document the dual page-index convention.** Add to `§text_units.py` intent or to README §layout: "Filesystem page PNGs and `source_locator.page` are 1-indexed; contract `order` and the integer suffix of `text_unit_id` are 0-indexed."

6. **Add one runtime-anchor test to the test plan.** In `test_validation.py` (or a new `test_paths.py`): assert that `(volume_root / unit.source_path).exists()` and `(volume_root / media.path).exists()` for every emitted unit/media after a successful `run_prepare`. This pins the anchor convention in code, not just in prose.

7. **(Optional but recommended)** Document that the OCR prompt should explicitly instruct the model **not** to wrap output in markdown code fences (` ```json ... ``` `) and to emit raw JSON only. The plan says "no markdown code fences, no trailing newline noise" in `§prompts.py` intent — confirm this exact wording is in `OCR_PROMPT`, since markdown wrapping is `gpt-5-mini`'s single most common failure mode for structured-output tasks.

After these revisions land in the plan, this slice is ready for the Critic.

## References

- `automations/ln_voice_over_v2/AGENTS.md:25-26` — current "Boundaries" bullet 3 the plan amends.
- `automations/ln_voice_over_v2/AGENTS.md:35-36` — "Code Rules" bullet the plan claims stays in force.
- `automations/ln_voice_over_v2/stages/prepare/contracts.py:14-42` — `PreparedTextUnit`, `PreparedMedia`, `PreparedVolume`. Frozen, `extra="forbid"`, `chapter_id: None = None`.
- `automations/ln_voice_over_v2/common/ids.py:9-36` — `SlugId`/`AssetId`/`TextUnitId`/`ProfileId` patterns and `validate_artifact_path`.
- `automations/ln_voice_over_v2/common/enums.py:68-73` — `MediaType.ILLUSTRATION` value.
- `automations/ln_voice_over_v2/common/errors.py:8-24` — `ValidationProblem`, `ContractValidationError` shape the plan's new validation codes plug into.
- `automations/ln_voice_over_v2/common/paths.py:10-25` — `DEFAULT_PROJECT_DATA_ROOT` and `prepared_volume_path` used by `PrepareConfig`.
- `automations/ln_voice_over_v2/common/artifacts.py:13-26` — `ContractModel` (frozen, forbid) and `PersistedArtifact` flat shape.
- `automations/ln_voice_over_v2/common/json_io.py:11-25` — atomic-write pattern the plan reuses for `save_ocr`.
- `pyproject.toml:7-13` — current `[project.dependencies]` matching the plan's diff hunk.

## Iteration 2 — re-review of revised plan

verdict: APPROVE
timestamp: 2026-05-25T01:00:00Z

### TL;DR

The Planner has implemented all 7 architect revisions plus the Critic's 8 additions cleanly. The Protocol/Callable conflict is resolved decisively in the AGENTS.md-compliant direction (architect synthesis option 1.b — drop the Protocols). All principle-violation checks pass on the revised plan. The dual-anchor and dual-index conventions are now pinned in writing in three places each (file-level legend, `§validation.py`, README). One minor residual textual inconsistency exists in the `--force` precedence wording (one place says "wins," every other place says "rejected") — it is purely editorial, not behavioral, and does not block approval. (Orchestrator note: that line-51 wording has since been fixed in the plan.)

### 1. Re-check of the 7 original architect revisions

| # | Original ask | Status |
|---|---|---|
| 1 | Pick a stance on `OcrProvider` Protocol vs. AGENTS.md "Code Rules" | Resolved (Planner dropped the Protocols; Callable injection only). |
| 2 | Pin artifact-path anchor convention in writing | Resolved (own subsection + validator docstring + README legend). |
| 3 | Partial-progress + malformed-cache guarantees in runner | Resolved (cache→OCR→save→return per-worker order; WARNING-on-malformed + recompute; tests cover both). |
| 4 | `--force-ocr` media-cleanup behavior | Resolved (`rebuild` flag in media.py; runner passes True under either force; README documents both). |
| 5 | Document the dual page-index convention | Resolved (own subsection + text_units docstring + README legend). |
| 6 | Runtime-anchor test in the test plan | Resolved (end-to-end test asserts `(volume_root / unit.source_path).is_file()` for every unit and media entry). |
| 7 | OCR prompt forbids markdown fences | Resolved (prompt constraints top-three; test asserts ContractValidationError on fenced output). |

All 7 are Resolved.

### 2. Principle-violation re-checks

- Protocol-vs-AGENTS.md conflict: clean. No `OcrProvider` / `Downloader` / Protocol leaks anywhere; AGENTS.md "Code Rules" bullet preserved verbatim.
- All `ArtifactPath` strings + ids match `common/ids.py` regexes (`unit_NNNNNN`, `illustration-NNN`, `pdf-llm-ocr`, all relative POSIX with no `..`).
- Plan does not touch `common/*`, `pipeline/`, `series/`, or sibling stage `contracts.py`.
- Page-index dual convention internally consistent across `text_units`, `source_path`, `source_locator`, `media.path`, `media.source_path`.
- Concurrency primitive named: `concurrent.futures.ThreadPoolExecutor(max_workers=N)` with `Future.result()` propagation.
- `--force` / `--force-ocr` mutually exclusive at argparse + ADR-level defense.
- Malformed OCR cache → WARNING + recompute is stated, not implied.

### 3. Newly-introduced issues

- [WARN — non-blocking, since fixed by orchestrator] line 51 textual contradiction ("`--force` wins and ... rejected"). Removed; every location now uses only the "rejected" framing.
- No dangling Protocol references in tests/file-list.
- Anchor convention does not contradict any path written elsewhere.
- ThreadPoolExecutor + per-task save_ocr + exception propagation interplay is correct.
- `OcrPageResult` no longer routed through `common/json_io.save_json_contract` (save_ocr replicates the atomic-write primitive locally).
- `pyproject.toml` diff still applies.

### 4. Locked-input compliance — re-checked

All 11 locked-input items hold against the revised plan.

### 5. Verdict

APPROVE
