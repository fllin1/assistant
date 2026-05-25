---
role: critic
target_plan: lnvo-v2-prepare-step1.md
target_architect_review: lnvo-v2-prepare-step1.architect.md
timestamp: 2026-05-25T00:00:00Z
verdict: ITERATE
---

# Critic Review — LNVO v2 Prepare Step 1

## TL;DR

The plan is structurally sound, respects every locked input, and leaves `common/*` and sibling stage contracts untouched. Verdict is **ITERATE**, not **REJECT**: the gaps are concrete and fixable in one pass. There are no hidden contract violations — the architect's "[BLOCKER]" on `prepared/media/...` is overstated (the path passes `validate_artifact_path`; the real defect is that the **anchor convention is implicit**). The single real architectural risk is the `OcrProvider` Protocol vs. the `AGENTS.md` "Code Rules" prohibition on empty ports; the Planner currently asserts the exception in prose but the AGENTS.md amendment itself does not authorize it. Beyond that, the plan has four under-specified operational behaviors (malformed-cache logging, partial-progress write ordering, `--force-ocr` media cleanup, concurrency mechanism) and one missing test (artifact-path-anchor round-trip).

Mode: **THOROUGH**. No escalation to ADVERSARIAL — findings are concentrated and isolated, not systemic.

## Pre-commitment predictions

Before reading the artifacts I predicted these high-likelihood problem areas for a contract-first prepare-stage plan:

1. Identifier or path-validator regex drift (plan IDs not matching `common/ids.py`).
2. Anchor convention for `ArtifactPath` left implicit; downstream stage will mis-resolve.
3. OCR retry / malformed-JSON failure path under-specified.
4. Resume semantics for partial state under-specified, especially media cleanup on re-OCR.
5. Premature abstraction tension (Protocol vs. function) given the package's stated "no empty ports" rule.

Findings vs. predictions: 1 → no violation (verified); 2 → confirmed (anchor implicit); 3 → confirmed (no retry, no logging); 4 → confirmed (media-cleanup-on-`--force-ocr` undefined); 5 → confirmed (the load-bearing item architect raised). Pre-commitment matched the actual finding set well; no surprises emerged outside it.

## 1. Verification of locked-input fidelity

Per-input citations (plan section / line in plan):

- **One text_unit per page** — `§text_units.py` (plan:253-259) emits `(page, OcrPageResult)` → one `PreparedTextUnit` each, `order=page-1`, ids `unit_{page-1:06d}`. PASS.
- **`media` = only auto-detected illustrations** — `§media.py` (plan:236-247) only emits a row when `is_illustration == true`. PASS.
- **`source_profile = "pdf-llm-ocr"`** — Asserted in `test_runner_end_to_end.py` (plan:400) and in the manual-smoke invariant (plan:434). The `PrepareResult.prepared_volume` field is set by the runner, but the constant string is not pinned anywhere in `§runner.py` intent. **MINOR**: name the constant in `§runner.py` (e.g. "Always sets `prepared.source_profile = 'pdf-llm-ocr'` regardless of CLI flags").
- **Default `story_profile = series` id** — `PrepareConfig.story_profile: ProfileId | None = None  # defaults to series` (plan:131) and asserted in `test_runner_end_to_end.py` (plan:401). PASS.
- **OCR via `codex exec`, default `gpt-5-mini`** — `CodexExecOcrProvider(model="gpt-5-mini", executable="codex", …)` (plan:220-227) and argv spelled out at plan:230. PASS.
- **Downloader = external CLI behind boundary** — `§downloader.py` (plan:154-174). PASS.
- **Rasterizer = PyMuPDF** — `§rasterizer.py` (plan:179-195) + pyproject diff (plan:293-301). PASS.
- **Full cache + resume-by-default with `--force`** — `--force` and `--force-ocr` flags (plan:114, 132-134, 342-346). PASS, with a gap on `--force-ocr` media semantics — see §3 below.
- **Validation = Pydantic + disk-existence** — `§validation.py` (plan:264-276) explicitly says "Pydantic-level validation is already enforced … this function only adds filesystem-cross-checks." PASS.
- **Default concurrency = 4** — `PrepareConfig.workers: int = 4` (plan:131), CLI `--workers` default 4 (plan:114). PASS.
- **Strict OCR JSON `{"transcript": str, "is_illustration": bool}`** — `OcrPageResult(BaseModel, frozen=True, extra="forbid", transcript=str, is_illustration=bool)` (plan:209-213). PASS.

All eleven locked inputs are realized in writing. No drift.

## 2. Verification of architect's specific claims against actual source

I re-checked every contract claim the architect made:

- `common/ids.py:21-33` `validate_artifact_path` — confirmed: rejects empty, leading `/`, `\`, and any part in `{"", ".", ".."}`. `prepared/media/illustration-001.png` and `source/pages/001.png` **PASS** the validator. The architect's "[BLOCKER]" framing is misleading; the actual issue (and the one the architect ultimately argues for in the action item) is that the **anchor convention is implicit**, not that the path is invalid. I downgrade this from "BLOCKER" to a documentation-pinning defect. Keeping it as a Major finding because Transform will guess wrong without it.
- `common/ids.py:9` `SlugId` `^[a-z0-9][a-z0-9-]*$` — `illustration-001` matches (begins with lowercase letter, contains only `[a-z0-9-]`). PASS.
- `common/ids.py:15` `TextUnitId` `^unit_[0-9]{6}$` — `unit_000000` matches. PASS.
- `common/enums.py:73` `MediaType.ILLUSTRATION = "illustration"` — confirmed. PASS.
- `common/enums.py:39` `ArtifactKind.PREPARED_VOLUME = "prepared_volume"` — confirmed; `stages/prepare/contracts.py:37` sets it as `Literal[ArtifactKind.PREPARED_VOLUME]`. PASS.
- `stages/prepare/contracts.py:38` `chapter_id: None = None` — confirmed; plan never sets `chapter_id`. PASS.
- `common/paths.py:10, 18, 23-25` — `DEFAULT_PROJECT_DATA_ROOT`, `volume_root`, `prepared_volume_path` exist with the signatures the plan assumes. PASS.
- `common/artifacts.py:13-26` — `ContractModel` is frozen + extra=forbid; `PersistedArtifact` carries `schema_version`/`artifact_kind`/`series`/`volume`/`chapter_id`. Plan honors all of this via the existing `PreparedVolume` model. PASS.
- `common/errors.py:8-24` — `ValidationProblem(code, message, path)` and `ContractValidationError(problems: list[…])`. Plan's `§validation.py` codes plug into this shape correctly. PASS.
- `pyproject.toml:7-13` — the dependency list matches the plan's diff context exactly. PASS.
- `AGENTS.md:25-26` (current "Boundaries" bullet 3) — the plan's "Current paragraph" quote at plan:81-84 matches the file verbatim. PASS.
- `AGENTS.md:35-36` (current "Code Rules" bullet on empty ports) — confirmed; the plan's claim at plan:101 that this rule "stays" is the load-bearing assertion architect flagged. See §3 Finding C1 below.

No contract violation introduced. The plan's `volume.json`-relative paths (`source/pages/{page:03d}.png`, `prepared/media/illustration-{seq:03d}.png`) sit under `volume_root(data_root, series, volume)`, which is the directory **two levels above** the artifact (`volume_root / "prepared" / "volume.json"`). This is a defensible convention, but it is nowhere written down.

## 3. Critical findings (block execution)

### Finding C1 — AGENTS.md "Code Rules" prohibition vs. `OcrProvider` Protocol is unauthorized in the AGENTS.md amendment

- **Evidence (plan):** plan:88-99 (the proposed AGENTS.md replacement) modifies only the "Boundaries" bullet, not the "Code Rules" bullet. Plan:101 explicitly says: `"The 'Code Rules' section's prohibition on 'empty runners, ports, adapters, or services' stays — Prepare's runner and boundaries are non-empty by construction."`
- **Evidence (source):** `automations/ln_voice_over_v2/AGENTS.md:35-36`: `"Do not add empty runners, ports, adapters, or services until a later slice has real orchestration or external-boundary behavior to represent."`
- **Why this matters:** `class OcrProvider(Protocol)` (plan:215-218) has **exactly one** implementation in this slice (`CodexExecOcrProvider`). Out-of-scope item #4 (plan:450) explicitly rules out a second OCR backend. Reasonable readers will disagree on whether a Protocol with one default-implementing dataclass is "empty" or "a named boundary with one default." The plan's interpretation is plausible but not authorized in writing. The architect's Tension 1 is correct: either the Protocol must go, or the AGENTS.md amendment must explicitly carve out the exception with a justification.
- **Confidence:** HIGH. Author cannot refute — the AGENTS.md amendment as written does not authorize the interpretation the runtime relies on.
- **Realist check:** Real-world worst case is not data loss or security; it is a future reader (Codex implementer for Transform, or human reviewer) reasonably refusing the merge because the codified rule and the new code disagree. Mitigated by: this is caught at plan review, not at runtime. But it remains CRITICAL because it is the largest principle/contract-vs-plan inconsistency in the package and silently dropping a stated rule is exactly what the contract skeleton was created to prevent. Severity retained.
- **Fix:** Adopt one of the architect's two syntheses, atomic and explicit:
  - (a) Drop `OcrProvider(Protocol)` and `Downloader(Protocol)`. Define `ocr_page(page_image, *, model, executable, timeout_seconds, prompt) -> OcrPageResult` and `download_anyflip(url, dest, *, executable, timeout_seconds) -> None` as free functions in `ocr.py` / `downloader.py`. Let `run_prepare` accept `ocr_fn: Callable[[Path], OcrPageResult] | None = None` and `download_fn: Callable[[str, Path], None] | None = None`. Or
  - (b) Keep both Protocols and add a third bullet to the AGENTS.md amendment naming the carve-out: `"A Protocol introduced alongside a single concrete default implementation in this slice (e.g. OcrProvider + CodexExecOcrProvider, Downloader + AnyflipDownloader) is a named external boundary, not an 'empty port' under the Code Rules. Adding a second implementation does not require revisiting this bullet."`
  Either is acceptable; pick one and apply it consistently to both `OcrProvider` and `Downloader`.

## 4. Major findings (significant rework)

### Finding M1 — Artifact-path anchor convention is implicit

- **Evidence (plan):** plan:247 says `path="prepared/media/illustration-{seq:03d}.png"`, `source_path="source/pages/{page:03d}.png"`. Plan:259 sets `source_path=f"source/pages/{page:03d}.png"`. The validation gate (plan:274-275) says paths "resolve under `volume_root`" but the anchor `volume_root` is never named in `§validation.py` or `§runner.py` intent.
- **Evidence (source):** `common/paths.py:18-25` — `volume_root(data_root, series, volume) = data_root / series / volume`, and `prepared_volume_path = volume_root / "prepared" / "volume.json"`. The natural reader assumption is that `ArtifactPath` values inside `volume.json` are relative to the artifact's parent (`prepared/`), but the plan intends them relative to `volume_root` (two levels up).
- **Why this matters:** Transform (Step 2) will read `volume.json` and join paths somewhere. If it picks the wrong anchor, every `text_unit.source_path` will miss. This is the kind of latent contract ambiguity that a contract-first skeleton exists to prevent.
- **Confidence:** HIGH.
- **Fix:** Add one sentence to `§validation.py` intent and to `§runner.py` intent: `"Every ArtifactPath in volume.json is POSIX-relative to volume_root(data_root, series, volume) — i.e. the directory that contains both source/ and prepared/. validate_prepared_volume asserts (volume_root / path).is_file() for every embedded path."` Also add this to README §Expected runtime layout as a single-line legend.

### Finding M2 — Test plan does not pin the anchor convention

- **Evidence (plan):** Test files listed at plan:351-403. `test_validation.py` (plan:384-389) tests missing-file codes via mocks, but no test asserts that `(volume_root / unit.source_path).is_file()` and `(volume_root / media.path).is_file()` for the **happy path** end-to-end. `test_runner_end_to_end.py` (plan:397-402) round-trips the contract but does not assert filesystem joinability.
- **Why this matters:** The convention from M1 must be enforced in code, not only in prose; otherwise a future refactor can silently break it.
- **Confidence:** HIGH.
- **Fix:** In `test_runner_end_to_end.py`, add: `"After run_prepare returns, for every unit in prepared.text_units and every media in prepared.media, assert (volume_root / unit.source_path).is_file() and (volume_root / media.path).is_file() and (volume_root / media.source_path).is_file()."`

### Finding M3 — `--force-ocr` media-cleanup semantics undefined

- **Evidence (plan):** Plan:345 says `--force-ocr` recomputes every page's OCR, reuses `source/volume.pdf` and `source/pages/*.png`. Plan:247 says `collect_media` "overwrites when `force`." Nothing in the plan describes what happens to **existing** `prepared/media/illustration-*.png` files under `--force-ocr` when the new OCR pass produces a **different** illustration map (e.g. page 47 was flagged on the old run but not on the new one).
- **Why this matters:** A stale `illustration-013.png` left on disk that no longer corresponds to any `PreparedMedia` row is a contract-vs-filesystem desync. `validate_prepared_volume` will not catch it (it only checks that every contracted path exists, not that every on-disk file is contracted). Downstream Scenes would not see it either, but a follow-up `--force` run would, and the asymmetry between the two force flags is surprising.
- **Confidence:** HIGH. Author cannot easily refute — the spec genuinely omits this.
- **Fix:** Add to README §Re-run flags and to `§media.py` intent: `"Under --force-ocr (and under --force), prepared/media/ is rebuilt from the new OCR pass: existing illustration-*.png files for pages no longer flagged as is_illustration are deleted before the new set is copied in. Under default resume, prepared/media/ is left alone unless the OCR pass for any page changes its is_illustration verdict."`

### Finding M4 — Partial-progress write guarantee under concurrency is implicit

- **Evidence (plan):** Plan:131 sets `workers=4`. Plan:230-231 says `CodexExecOcrProvider.ocr_page` has "No retries." Plan:392-395 (`test_runner_resume.py`) tests that pre-existing valid cache is reused but does not test that mid-run successes are committed before sibling failures abort.
- **Why this matters:** With 4 concurrent subprocess workers and "no retry," one malformed-JSON page aborts the run. If the runner joins all futures first and writes after the join, up to 3 successful in-flight pages will not be cached and will be re-spent on the next run. On a 200-page volume at gpt-5-mini rates this is real money. The architect raised this; I confirm it is real.
- **Confidence:** HIGH.
- **Fix:** Add to `§runner.py` intent: `"Each per-page future writes source/ocr/{page:03d}.json to disk on success before awaiting any sibling. A sibling failure does not roll back already-written pages. Implementation note: use concurrent.futures.ThreadPoolExecutor(max_workers=config.workers) and call save_ocr inside the per-page task, not after .result() returns to the join site."` Add a test in `test_runner_resume.py`: `"If page 2 raises but page 1 succeeds, source/ocr/001.json exists after the run aborts; on the next invocation (no --force), page 1 is not re-OCR'd."`

### Finding M5 — Malformed-cache silent-recompute hides corruption causes

- **Evidence (plan):** Plan:392-395 (`test_runner_resume.py`) says: `"Pre-existing invalid source/ocr/{page:03d}.json is recomputed (the stub OcrProvider is called). Justification: this matches per-page resume semantics from locked input #11 — a corrupted cache file is no different from an absent one."` Plan:232 says `load_cached_ocr` "returns `None` if the file does not exist or fails validation" — the caller cannot distinguish the two reasons.
- **Why this matters:** Silent recompute on a malformed cache hides whether the corruption is from (a) a crashed prior run, (b) a JSON-schema regression, or (c) a different OCR model writing an incompatible shape. On (c), the user will burn the OCR budget every run until they notice.
- **Confidence:** HIGH.
- **Fix:** Either return a discriminated result from `load_cached_ocr` (e.g. `LoadResult = Literal["missing", "malformed"] | OcrPageResult`) or have the runner detect "file exists but `load_cached_ocr` returned None" and emit `"[prepare] source/ocr/{page:03d}.json failed strict parse; recomputing"` to stderr/log. Two-line change. Add a test in `test_runner_resume.py` asserting the warning is emitted exactly once per malformed cache file.

### Finding M6 — Concurrency mechanism not pinned in `§runner.py`

- **Evidence (plan):** Plan:131 declares `workers: int = 4` but plan:119-152 (`§runner.py` public surface) does not say whether concurrency is `ThreadPoolExecutor`, `ProcessPoolExecutor`, `asyncio.gather` with `asyncio.to_thread`, or sequential with a `workers=1` shortcut. Codex implementer choice matters: `ProcessPoolExecutor` and `asyncio` have very different failure-isolation properties for subprocess OCR.
- **Why this matters:** Two implementers will pick differently. The malformed-page failure path differs across pools (process pool vs thread pool propagate exceptions differently across the join boundary).
- **Confidence:** MEDIUM-HIGH.
- **Fix:** Add to `§runner.py` intent: `"Concurrency is implemented via concurrent.futures.ThreadPoolExecutor(max_workers=config.workers). codex exec is a child process, so thread-based fan-out gives correct isolation without paying ProcessPoolExecutor's pickling cost."` One sentence.

## 5. Minor findings

- **m1.** `OcrPageResult` is not a `PersistedArtifact`/`ContractModel`, so it cannot reuse `common/json_io.py:save_json_contract` directly (it has no `schema_version`/`artifact_kind`). The plan's `save_ocr` (plan:232) needs to replicate the `tempfile.NamedTemporaryFile` + `tmp_path.replace(path)` primitive locally. Just say so in `§ocr.py` intent so the implementer does not try to call `save_json_contract`.
- **m2.** Plan:114 lists `--workers` and `--ocr-model` as CLI flags but the README's "Optional flags" line at plan:328 spells them correctly; no drift, but `--story-profile` arg-parsing must produce a `ProfileId` (i.e. the argparse layer must accept the string and let the Pydantic constructor's regex enforce validity — say so once in `§__main__.py` intent so the implementer does not import the regex into argparse).
- **m3.** Plan:230 hard-codes the argv `"--ephemeral"` flag for `codex exec`. If `codex` rejects unknown flags on the user's installed version, this fails opaquely. Not a blocker, but add to Open Questions: `"The codex exec flag set (-i, -m, --ephemeral, --skip-git-repo-check, -s read-only) is locked at the plan level. If a newer/older codex CLI version drops or renames one of these, the runner must surface a clear error rather than a generic non-zero-exit."`
- **m4.** Plan:259 says `source_locator={"page": page}`. `PreparedTextUnit.source_locator` is typed `dict[str, str | int | float | bool | None]` (`contracts.py:21`) — `int` is allowed. PASS, but spell out in `§text_units.py` intent that `page` is the **1-indexed** filesystem page number, so the architect's [WARN] on dual conventions is closed in writing.
- **m5.** Plan:334-340 (README layout block) is unambiguous about filesystem layout but does not name the "every embedded path is relative to volume_root" rule. Repeat it there (one line) so the contract reader does not have to derive it.
- **m6.** Plan:393 says "stub OcrProvider is asserted NOT called for that page" — this assumes the test fake is a Protocol-typed mock. If the Protocol is dropped per Finding C1 option (a), the test becomes "`ocr_fn` Callable is asserted NOT called for that page." Cosmetic only; just rephrase if Protocol goes.

## 6. What's missing (gaps)

- No mention of **stdout/stderr handling** for `codex exec`. Plan:231 says "capture stdout, strip whitespace, then `OcrPageResult.model_validate_json(stdout)`." What about stderr? Codex CLI writes progress and warnings to stderr; if any of that leaks into stdout (multi-stream buffering on macOS pipes), `model_validate_json` fails and the page is reported as `ocr_malformed`. Add to `§ocr.py` intent: `"subprocess.run with stdout=PIPE, stderr=PIPE, text=True; only stdout is parsed; stderr is included in the ContractValidationError message on failure for debuggability."`
- No mention of **PNG color mode** in `§rasterizer.py`. The plan says "RGB PNG" (plan:195) but does not pin alpha or DPI per-axis. PyMuPDF's `Pixmap(matrix=..., alpha=False)` is the canonical RGB-no-alpha render. State it.
- No mention of **page-count sanity check** anywhere. After `rasterize_pdf`, the runner should reject a PDF with zero pages (or with page count below some sane floor like 1) with a typed error before spending OCR budget.
- No mention of **stable order** between `rasterized` and `ocr_results` in `§media.py:zip` (plan:247). The plan asserts "same length, same 1-indexed page order" but doesn't say where that order is established. The runner must guarantee it; spell it out in `§runner.py`.
- No mention of **logging configuration**. The malformed-cache warning and the "page N succeeded / page M failed" progress need somewhere to go. Either pick `logging.getLogger("ln_voice_over_v2.prepare")` or use plain stderr-print with a prefix; the plan currently picks neither.
- No mention of **`source_locator` keys beyond `page`**. Transform may want `column_hint`, `dpi`, or `pdf_bookmark` later — out of scope for this slice, but worth one line in Open Questions confirming `source_locator` is intentionally minimal in Step 1.

## 7. Ambiguity risks

- Plan:230 argv: `"... '-s', 'read-only', self.prompt]"` → **Interpretation A:** the prompt is one positional argv element after all flags. **Interpretation B:** the prompt is the positional argument before any image flag. The argv shape is locked at plan level so this is fine, but the implementer should confirm that `codex exec` accepts the prompt as the trailing positional and not as `--prompt`. Risk if wrong: every OCR call fails with a CLI argument error and the runner emits `ocr_malformed` for every page. (Minor — caught immediately in manual smoke test.)
- Plan:344 `"(no flag) per-page resume — keeps any source/ocr/{page:03d}.json that already parses to the strict contract"` → **Interpretation A:** "parses" means `model_validate_json` succeeds. **Interpretation B:** "parses" means the file is JSON (no schema check). The plan strongly implies A (because of `extra="forbid"`) but does not say so. Risk if B is chosen: a JSON file with extra keys is reused, then `PreparedTextUnit`'s downstream consumer trips. Fix: say "parses via `OcrPageResult.model_validate_json`."
- Plan:142 `PrepareResult.page_count` → **Interpretation A:** number of pages in the PDF (`len(rasterized)`). **Interpretation B:** number of `text_units` emitted (`len(prepared.text_units)`). These are equal by design (one text_unit per page) but the plan does not say which the field reports. Risk if they ever diverge (page raster fails for one page): silent skew. Pin one source of truth.

## 8. Architect-feedback-addressed audit

The Planner has not yet revised the plan, so every architect-requested revision is **Unresolved**. Status table:

| # | Architect revision | Status |
|---|---|---|
| 1 | Pick a stance on `OcrProvider` Protocol vs. AGENTS.md "Code Rules" | Unresolved |
| 2 | Pin artifact-path anchor convention in writing | Unresolved |
| 3 | Specify partial-progress + malformed-cache guarantees in `§runner.py` | Unresolved |
| 4 | Specify `--force-ocr` media-cleanup behavior | Unresolved |
| 5 | Document dual page-index convention | Unresolved |
| 6 | Add runtime-anchor test to test plan | Unresolved |
| 7 | (Optional) OCR prompt must instruct "no markdown fences" | Unresolved (already present in `§prompts.py` intent at plan:203 as prose; still missing as a written-down test in `test_ocr_provider.py` — the existing markdown-fence test (plan:370) asserts the parser rejects fenced output but does not assert the prompt explicitly forbids them) |

## 9. Acceptance-criteria audit

- Every listed test has a clear given/expect shape (plan:355-402). PASS.
- The manual smoke test names exact files and a one-line invariant (plan:419-435). PASS.
- The plan does not punt to "looks reasonable" — the success invariant is a Python assert on a strict round-trip. PASS.
- Pytest invocation paths are exact: tests live at `tests/automations/ln_voice_over_v2/stages/prepare/` (plan:352). PASS. Add `pytest tests/automations/ln_voice_over_v2/stages/prepare/` as the explicit command in README §Test plan to remove the last drop of ambiguity.

## 10. Risk-mitigation audit (gate)

Checking the six risks the Critic mandate enumerates:

| Risk | Addressed in plan? | Where |
|---|---|---|
| `codex exec` non-JSON / extra-key output | YES | `§ocr.py:231` (`ContractValidationError(code="ocr_malformed")`); `test_ocr_provider.py:370` (markdown-fence test); `OcrPageResult` is `extra="forbid"`. |
| PyMuPDF DPI default + size/OCR-quality tradeoff | PARTIAL | `§rasterizer.py:191` locks 200 DPI; Open Question #1 documents the tradeoff. No explicit smoke-test step to verify quality at 200 DPI. **Action:** add a smoke-test sub-step: "If the first 5 pages of `source/ocr/*.json` contain garbled kana, re-run with `dpi=300` (currently requires editing `rasterize_pdf` default — Step 2 may expose as a CLI flag)." |
| `anyflip-downloader` failure (network/login/captcha) | WEAK | `§downloader.py:174` says "Raise `RuntimeError` on non-zero exit." No mention of the user-facing diagnostic when the CLI exits zero but produces no PDF (the more common silent-failure mode). **Action:** add to `§downloader.py` intent: `"After the subprocess returns successfully, assert dest_pdf exists and is non-empty (size > 0); otherwise raise RuntimeError with the captured stderr."` |
| Partial run after rasterize but before OCR — `--force-ocr` semantics | PARTIAL | Plan:345 covers the OCR-reuse path; plan does NOT cover the symmetric case where rasterization succeeded but the prior run aborted before writing any OCR. Resume should handle it naturally (cache miss → OCR), but no test asserts it. **Action:** add a test: `"If source/pages/*.png exists but source/ocr/ is empty, default (no-flag) run produces a complete prepared volume without re-rasterizing."` |
| Two-column / RTL layout in OCR prompt | YES | `§prompts.py:203` documents the rule ("both columns top-to-bottom then left-to-right"). Open Question #3 acknowledges no automated check is feasible. PASS. |
| Concurrent file writes when `--force` and resume run together | NOT ADDRESSED | `--force` and resume are mutually exclusive at the flag level (resume is the default when neither is set), so the "both at once" case is structurally impossible — but the plan does not say so. **Action:** add to `§runner.py` intent: `"--force, --force-ocr, and the implicit resume default are mutually exclusive at the CLI; --force implies recomputing OCR, so --force-ocr is silently ignored when both are passed."` Or have `__main__.py` reject `--force --force-ocr` together as a usage error. |

## 11. Out-of-scope discipline

Plan:443-452 explicitly enumerates out-of-scope items: Transform, Dialogue, Scenes, Generation, legacy migration, non-AnyFlip sources, non-PDF inputs, manual-review UI, retry/backoff, multi-volume URLs, translation. Nothing in the file-level change list (plan:107-285) touches any of those. PASS.

The Open Questions section (plan:456-464) carefully defers cross-stage concerns ("Empty-transcript illustration units" → "Confirm during Step 2 planning, not now"). PASS.

## 12. Premature-abstraction check

The plan introduces exactly the two named boundaries (`OcrProvider`, `Downloader`) and no other ports/adapters/services/factories. PASS on the named scope. The contested question is whether *those two* are themselves premature — that is Finding C1, not a separate finding.

## 13. Self-audit

Re-read of every finding:

- **C1** (Protocol vs. AGENTS.md): HIGH confidence; author cannot refute (the AGENTS.md amendment as written does not authorize the carve-out); FLAW not preference. Keep at CRITICAL.
- **M1** (anchor convention implicit): HIGH; cannot be refuted by reading the plan alone; FLAW. Keep at MAJOR.
- **M2** (no anchor test): HIGH; FLAW. Keep at MAJOR.
- **M3** (`--force-ocr` media cleanup): HIGH; FLAW. Keep at MAJOR.
- **M4** (partial-progress writes): HIGH; FLAW. Keep at MAJOR.
- **M5** (malformed-cache silent recompute): MEDIUM-HIGH; could be refuted with "user is expected to inspect their logs anyway" — but `§ocr.py` does not even define a logger. Keep at MAJOR.
- **M6** (concurrency mechanism not pinned): MEDIUM-HIGH; arguably the implementer should just pick; but the plan's "Codex-implementer ready" principle (plan:18) means the choice should be in the plan. Keep at MAJOR.
- **m1-m6** (minors): all checked; none promoted; none demoted.

## 14. Realist check

- **C1**: Worst case is a downstream reader (or the architect on next pass) blocking on the principle conflict. Mitigated by: caught at plan review, not runtime. Mitigated by: the contract layer itself is untouched (no contract harm done). Still CRITICAL because the package's own "no empty ports until needed" rule is the load-bearing principle of the contract skeleton, and silently violating it on the first implementation slice sets the worst possible precedent. **Mitigated by: plan-review-stage catch, but severity retained because principle-precedent risk is real.**
- **M1/M2**: Worst case is Transform Step 2 mis-resolves paths on its first run, caught immediately by a unit test or by `validate_prepared_volume`. **Mitigated by: Step 2 has its own plan/review/critic cycle.** Detection is fast. MAJOR retained.
- **M3**: Worst case is a stale `illustration-013.png` sits on disk; nothing immediately observable until the next stage tries to enumerate `prepared/media/`. **Mitigated by: contracts are the source of truth (no stage reads the directory listing).** MAJOR retained — still affects user trust in `--force-ocr`'s idempotency.
- **M4**: Worst case on a 200-page volume is $5-$15 of avoidable OCR cost per crash. **Mitigated by: real-world crash frequency on `codex exec` is unknown; could be once-per-100-runs or once-per-2-runs.** Not downgraded because OCR cost is the user-visible cost driver of this entire stage.
- **M5**: Worst case is silent budget burn on a JSON-schema regression. **Mitigated by: the schema is locked at this slice and unlikely to change for a while.** Could be downgraded to MINOR — but the fix is two lines, so the cost of "keep at MAJOR" is trivial. Keep at MAJOR.
- **M6**: Worst case is the implementer picks `ProcessPoolExecutor` and pays a 10-100ms pickling penalty per page. **Mitigated by: penalty is small in absolute terms.** Could be downgraded to MINOR. Keep at MAJOR because failure-isolation semantics differ across pools and that is what made M4 hazardous in the first place.

No downgrades applied. Recalibration: none.

## 15. Multi-perspective notes

- **Executor:** "Can I write this without asking?" Mostly yes, but I do not know which concurrency primitive to use (M6), whether to delete stale media on `--force-ocr` (M3), whether to log malformed-cache recomputes (M5), and what to anchor `ArtifactPath` to (M1). All four answers are one sentence each in the plan.
- **Stakeholder:** Does this solve the problem? Yes — one AnyFlip URL in, one `PreparedVolume` out, all locked inputs honored, contracts untouched. Scope is appropriate. Success criteria are measurable.
- **Skeptic:** Strongest argument against this plan: the `OcrProvider` Protocol is a port being introduced before its second implementation exists, in a package whose own rules forbid that pattern. The plan's response ("non-empty by construction") is debatable. The architect-suggested syntheses are both cheaper than letting this go to merge with the principle conflict unresolved.

## 16. Verdict

```
ITERATE
```

The plan respects every locked input and breaks no contract. It is, however, blocked on one principle conflict (C1) and six concrete operational under-specifications (M1-M6) that together prevent a Codex implementer from coding it without asking questions — which violates the plan's own "Codex-implementer ready" principle at plan:18.

After the merged revisions below land, this slice should be ready for ACCEPT.

## 17. Merged required revisions (deduplicated from architect + critic)

These are the atomic, action-leading revisions the Planner must apply. Architect items are kept where they stand; critic items are folded in. Each names the target section in `lnvo-v2-prepare-step1.md`.

1. **Resolve the OcrProvider/Downloader Protocol vs. AGENTS.md "Code Rules" conflict** in `§AGENTS.md scope change`: either drop both Protocols in favor of `Callable[[Path], OcrPageResult]` and `Callable[[str, Path], None]` injection seams (and update `§ocr.py`, `§downloader.py`, `§runner.py`, and all relevant tests), or add a third bullet to the AGENTS.md amendment authorizing the "named external boundary with one default" carve-out and citing the existing rule by name. (Architect #1 + Critic C1.)
2. **Pin the artifact-path anchor convention** in `§validation.py` intent and in `§runner.py` intent: every `ArtifactPath` in `volume.json` is POSIX-relative to `volume_root(data_root, series, volume)`. Repeat the rule as a one-line legend in README §Expected runtime layout. (Architect #2 + Critic M1.)
3. **Specify partial-progress and malformed-cache guarantees** in `§runner.py` intent: per-page futures write `source/ocr/{page:03d}.json` to disk on success before joining; sibling failure does not roll back committed pages; when `load_cached_ocr` returns `None` because of strict-parse failure (distinguishable from missing-file), emit one stderr `WARNING` line and recompute. (Architect #3 + Critic M4 + Critic M5.)
4. **Specify `--force-ocr` media-cleanup behavior** in README §Re-run flags and in `§media.py` intent: under `--force-ocr` (and under `--force`), `prepared/media/` is rebuilt from the new OCR pass — stale `illustration-*.png` files for pages no longer flagged are deleted before the new set is copied in. Default resume leaves `prepared/media/` alone unless an `is_illustration` verdict changes. (Architect #4 + Critic M3.)
5. **Document the dual page-index convention** in `§text_units.py` intent and in README §Expected runtime layout: filesystem page PNGs and `source_locator.page` are 1-indexed; contract `order` and the integer suffix of `text_unit_id` are 0-indexed. (Architect #5 + Critic m4.)
6. **Add runtime anchor + resume tests** to the test plan in `§test_runner_end_to_end.py` and `§test_runner_resume.py`:
   - After `run_prepare` returns, assert `(volume_root / unit.source_path).is_file()` and `(volume_root / media.path).is_file()` and `(volume_root / media.source_path).is_file()` for every unit/media.
   - If page 2's OCR raises but page 1 succeeds, `source/ocr/001.json` exists after the run aborts; a follow-up no-flag run does not re-OCR page 1.
   - If `source/pages/*.png` exists but `source/ocr/` is empty, default no-flag run produces a complete prepared volume without re-rasterizing.
   - If a `source/ocr/{page:03d}.json` exists but fails strict parse, the run emits exactly one `WARNING` line for that page and recomputes it. (Architect #6 + Critic M2 + Critic M4 + Critic M5.)
7. **Strengthen the OCR prompt and parser hardening** in `§prompts.py` intent and `§ocr.py` intent: the prompt must explicitly forbid markdown code fences and any preamble; the subprocess must capture stderr separately and include it in the `ContractValidationError` message on parse failure; `subprocess.run` uses `stdout=PIPE, stderr=PIPE, text=True`. (Architect #7 + Critic gap on stderr.)
8. **Pin the concurrency mechanism** in `§runner.py` intent: `concurrent.futures.ThreadPoolExecutor(max_workers=config.workers)`. Each per-page task calls `save_ocr` before returning so partial progress is durable. (Critic M6.)
9. **Define mutual-exclusion of re-run flags** in `§__main__.py` intent: passing both `--force` and `--force-ocr` is a usage error (argparse rejects it); the implicit default resume path is taken when neither is set. (Critic risk-mitigation gap.)
10. **Tighten the downloader failure mode** in `§downloader.py` intent: after a successful (zero-exit) `anyflip-downloader` invocation, assert `dest_pdf.is_file()` and `dest_pdf.stat().st_size > 0`; otherwise raise `RuntimeError` with the captured stderr. (Critic risk-mitigation gap.)
11. **Document `OcrPageResult` is not a `PersistedArtifact`** in `§ocr.py` intent: `save_ocr` and `load_cached_ocr` replicate the `tempfile.NamedTemporaryFile` + `tmp_path.replace(path)` atomic-write primitive locally; they do not call `common/json_io.save_json_contract`. (Critic m1.)
12. **State the `source_profile = "pdf-llm-ocr"` constant once in `§runner.py` intent** rather than only in the test assertions. (Critic locked-input audit.)
13. **Add `pytest tests/automations/ln_voice_over_v2/stages/prepare/` as the explicit verification command** in README §Test plan or in the Plan's Test plan section. (Critic acceptance-criteria audit.)
14. **Add Open Question about `codex exec` flag stability** to plan §Open Questions: the locked argv (`-i`, `-m`, `--ephemeral`, `--skip-git-repo-check`, `-s read-only`) assumes one `codex` CLI version; if the user's installed version differs, the runner must surface a clear error rather than a generic non-zero exit. (Critic m3.)
15. **Pin PNG color mode** in `§rasterizer.py` intent: render with `Pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), alpha=False)` (RGB, no alpha). (Critic gap.)

## Open questions (unscored)

- Is `gpt-5-mini` actually the user's intended default for this slice or a working name? Locked input #5 says so, but if the model id is wrong at codex-CLI lookup time the entire smoke run fails uniformly. Worth a one-line README note.
- Does `codex exec` accept the prompt as a trailing positional argument across the user's current codex version? The plan locks the argv at plan:230; the manual smoke test will discover any mismatch immediately.
- Is `200 DPI` the right default? The plan says yes for `gpt-5-mini`; if Open Question #1 of the plan (plan:460) bumps it to 300 DPI, file size goes up ~2.25× and OCR latency may increase. Decide once on a real volume before the architecture report on Step 2.

---

ITERATE — the plan is structurally correct and locked-input-faithful, but one principle conflict (OcrProvider Protocol vs. AGENTS.md Code Rules) and six concrete operational under-specifications must be resolved before a Codex implementer can ship it without asking questions.

## Iteration 2 — re-evaluation of revised plan

verdict: APPROVE
timestamp: 2026-05-25T01:30:00Z

15 / 15 merged revisions Resolved with line-level citations. Architect's iteration-2 APPROVE concurred on all 7 items.

No regressions:
- grep-verified zero live `OcrProvider` / `Downloader` / `CodexExecOcrProvider` / `AnyflipDownloader` references in signatures / file list / tests (only rejected options, disavowals, and future-follow-up notes remain).
- Every embedded path passes `validate_artifact_path`; every id matches its `common/ids.py` regex.
- Anchor convention restated identically in 10 locations (plan:5, 17, 24, 83, 129, 194, 349-352, 429, 518).
- `--force` / `--force-ocr` precedence stated identically in 5 locations (RALPLAN-DR E3 plan:51; ADR plan:77; `__main__.py` plan:148; README plan:438; test plan:507).
- `ThreadPoolExecutor` + per-task `save_ocr` + `Future.result()` exception semantics coherent; partial-progress test at plan:508 pins it in code.
- `OcrPageResult` correctly bypasses `common/json_io.save_json_contract` (plan:299).
- `SOURCE_PROFILE = "pdf-llm-ocr"` pinned as runner invariant (plan:157, 190).

APPROVE — every revision resolved with cited evidence, architect concurs, no regressions or new contract violations introduced.
