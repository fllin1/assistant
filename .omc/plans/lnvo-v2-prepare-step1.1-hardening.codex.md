# Step 1.1 Hardening — Codex implementation brief (single slice)

You are the implementer for LNVO v2 Step 1.1 (Prepare Hardening). The plan was produced by a ralplan consensus loop and approved by the user. Your job: implement every file change the plan specifies — source modules, doc updates, and tests — in one pass. The orchestrator (Claude Code) runs `uv sync` (if needed), `ruff format`, `ruff check`, `pytest`, and the commit afterwards. **Do not attempt `git`, `uv`, `pytest`, or `ruff` yourself** — the Codex sandbox blocks `.git/` writes and `uv` network calls, and you learned this in Step 1's slices. Spend your tokens on the writes.

## Context

- Repo: `/Users/regiswoof/_workspace/projects/assistant`
- Branch: `feat/lnvo-v2-prepare-step1` (HEAD `c6d387f`). Do not switch branches.
- Plan (read in full before touching any code): `.omc/plans/lnvo-v2-prepare-step1.1-hardening.md`
- Review files (for context only — do not modify): `.omc/plans/lnvo-v2-prepare-step1.1-hardening.architect.md`, `.omc/plans/lnvo-v2-prepare-step1.1-hardening.critic.md`
- The plan resolves a real bug observed in production: 5 of 318 OCR pages came back as refusal-style transcripts (`"Sorry, I can't ..."`), and the runner's "abort on first failure" policy then killed the assembly stage so `prepared/volume.json` was never written. The hardened runner must finish the run by emitting `needs_review: true` sentinel rows.

## In-tree files you must build against and NOT modify outside this slice

Already exists in current shape (read to confirm; build against the actual classes):

- `automations/ln_voice_over_v2/stages/prepare/prompts.py` — `OCR_PROMPT` constant (you will refactor this into the `OCR_PROMPTS` tuple per the plan).
- `automations/ln_voice_over_v2/stages/prepare/ocr.py` — `OcrPageResult` (Pydantic frozen, `extra="forbid"`, fields `transcript: str`, `is_illustration: bool`), `run_codex_ocr(...)`, `load_cached_ocr(...)`, `save_ocr(...)`.
- `automations/ln_voice_over_v2/stages/prepare/downloader.py`, `rasterizer.py`, `validation.py`, `media.py`, `__main__.py` — **do not modify**, no behavior change in this slice.
- `automations/ln_voice_over_v2/common/*` — **never modify**.
- `automations/ln_voice_over_v2/pipeline/`, `series/`, other `stages/*/contracts.py` — **never modify**.
- `pyproject.toml`, `uv.lock` — **never modify**.

## Files to change (the full Step 1.1 surface)

Source modules:

1. `automations/ln_voice_over_v2/stages/prepare/prompts.py` — define `OCR_PROMPTS: tuple[str, str, str]` per plan §`prompts.py`. Keep `OCR_PROMPT = OCR_PROMPTS[0]` as a back-compat alias. Use the exact verbatim text the plan provides for each index — do not paraphrase.

2. `automations/ln_voice_over_v2/stages/prepare/ocr.py` — add `_looks_like_refusal(transcript: str) -> bool` with the anchored regex; add `_is_failed_ocr(result: OcrPageResult) -> bool` as the runner's primary classifier (regex branch OR structural-sentinel `transcript == "" and is_illustration is False`). Implement per plan §`ocr.py`. Read the matrix at plan lines 376-386 carefully — it is your test specification. `run_codex_ocr` signature is unchanged.

3. `automations/ln_voice_over_v2/stages/prepare/runner.py` — implement the per-page retry loop, the `_OcrPageOutcome` private frozen dataclass, the structured collector replacing `[future.result() for future in futures]`, the two log lines (summary + needs-review listing), and the `build_text_units(...)` call updated with the new `needs_review` tuple argument. Implement per plan §`runner.py` line-by-line. **Important constraints:**
   - `_OcrPageOutcome` is module-private (leading underscore).
   - There is NO `_ocr_attempt(...)` wrapper. The default `ocr_fn` is built per attempt via the closure pattern in the plan (`_make_default_ocr_fn`, three `functools.partial` objects indexed by attempt).
   - Per-attempt `save_ocr(...)` happens BEFORE the worker returns, so partial progress is durable.
   - Semantic refusals (matches `_is_failed_ocr`) NEVER raise. Subprocess errors and JSON-parse failures still raise and still abort the run.
   - After the join, if `review_count > 0`, log `WARNING "prepare: %d page(s) need review: %s"` listing the page numbers. Always log `INFO "prepare: %d/%d pages OK, %d needs_review"` summary line.

4. `automations/ln_voice_over_v2/stages/prepare/text_units.py` — `build_text_units` adds a third parameter `needs_review: tuple[bool, ...]` (same length, same 1-indexed page order as `ocr_results` and `rasterized`). Each emitted `PreparedTextUnit` carries the matching `needs_review` value. Otherwise unchanged. **All call sites must be updated in the same commit** (atomic-commit grouping per plan §"Atomic commit grouping" lines 156-158) — both `runner.py` and `test_text_units.py`.

5. `automations/ln_voice_over_v2/stages/prepare/contracts.py` — add `needs_review: bool = False` to `PreparedTextUnit`. Additive optional. `extra="forbid"` and `frozen=True` semantics preserved. `schema_version` stays at 1 (do NOT bump).

Documentation:

6. `docs/lnvo/01-prepare.md` — add `needs_review` row to the "Prepared Text Unit" table per plan §"Contract change scope". Do NOT update the example JSON above the table (the plan justifies the omission at plan line 145).

7. `automations/ln_voice_over_v2/README.md` — add the one-sentence "Re-run flags" / "Prepare stage" addition per plan §`README.md`. (Pages that refuse OCR after 3 attempts are now saved with `needs_review: true` instead of aborting.)

Tests (under `tests/automations/ln_voice_over_v2/stages/prepare/`):

8. **Update** `test_text_units.py` — add the new `needs_review` parameter to every existing call site, including the contiguous-order invariant. Add at least one test that asserts `needs_review` is correctly threaded through (e.g. all-False, all-True, mixed).

9. **Update** `test_runner_end_to_end.py` — extend the anchor-convention assertion block to also assert `[unit.needs_review for unit in prepared.text_units]` is all `False` on the happy path.

10. **New** `test_refusal_detection.py` — implement Section A and Section B per plan §"New `test_refusal_detection.py`":
    - **Section A**: feed each of the 5 verbatim historical refusal transcripts to `_looks_like_refusal` and assert `True`. The exact strings (with the curly-quote `’` distinction) the plan specifies:
      - `"Sorry, I can't provide a full-page verbatim transcription of copyrighted text from the image."`
      - `"Sorry, I can't provide a full verbatim transcription of this page."`
      - `"I can't provide a full OCR transcription of this copyrighted book page. I can summarize it or transcribe a short excerpt."`
      - `"Sorry, I can't provide a full-page verbatim transcript of copyrighted text from the image. I can provide a short excerpt or a summary instead."`
      - `"Sorry, I can't provide a full verbatim OCR transcript of this copyrighted page. I can transcribe a short excerpt or summarize the page."`
      Plus 3 known-good controls that must assert `False`: a body-prose snippet (~250 words page-020-style), a dialogue snippet containing `"Sorry, but ..."` (page-027-style — must NOT match), a short chapter-break snippet (`"Page 59\ngito | mp4directs.com"` page-077-style).
      Use **ASCII straight apostrophes** in the regex per plan §"Apostrophe scope" line 195. The test data uses curly apostrophes (`’`) verbatim from disk — that means the production transcripts the user saw used the model's curly apostrophes. Confirm by reading two of the 5 cached files. If they use curly apostrophes, the regex MUST match them too — add the curly-apostrophe variant to the regex character class. Re-read plan line 195 and the historical transcript samples; if there is a conflict, **the live data wins** (the regex must match it).
    - **Section B**: implement the 6-row matrix at plan lines 376-386 as 6 named tests like `test_is_failed_ocr_<case>`. The row labels suggest names. Note the corrected whitespace-only row (Expected = `False`).

11. **New** `test_runner_retry.py` — implement the 9 scenarios per plan §"New `test_runner_retry.py`":
    - `test_retry_success_on_attempt_2`
    - `test_retry_success_on_attempt_3`
    - `test_retry_exhausted` (refusal × 3 → sentinel emitted, run completes)
    - `test_retry_exhausted_via_empty_sentinel` (model returns the sentinel-shaped JSON × 3)
    - `test_retry_exhausted_via_mixed_failure_shapes` (refusal-text + empty-sentinel mix)
    - `test_mixed_batch_partial_review`
    - `test_cache_with_refusal_recomputes`
    - `test_cache_with_empty_sentinel_recomputes`
    - `test_cache_with_legit_illustration_keeps_cache` (this one MUST assert `ocr_fn` is never called; use a `RuntimeError` side_effect)
    - `test_mutual_exclusion_force_and_force_ocr` (the existing argparse mutex; you may keep this in `test_runner_resume.py` if it already lives there — just don't break it)

    Use the precise `caplog` filter shape pinned at plan lines 394-404 — `levelname + substring + len == N` — not naive substring scans over the full caplog text. Inject `ocr_fn` and `download_fn` as test callables; never invoke the real `codex` CLI or real `anyflip-downloader`.

12. **New** `test_contracts.py` — implement the three named tests per plan §"New `test_contracts.py`" (plan lines 460-489):
    - `test_prepared_text_unit_defaults_needs_review_false` — `PreparedTextUnit.model_validate_json(...)` of a payload **without** the `needs_review` key succeeds and `unit.needs_review is False`.
    - `test_prepared_text_unit_round_trips_needs_review_true` — round-trip a payload with `needs_review: true`.
    - `test_prepared_text_unit_rejects_unknown_key` — `extra="forbid"` still rejects typos (e.g. `needs_reveiw`) with `ValidationError`.

## Hard constraints

- Do NOT modify any file outside the 11 named above.
- Do NOT add new dependencies. Stdlib `re`, `logging`, `concurrent.futures`, `functools`, `dataclasses`, `unittest.mock`.
- Do NOT introduce new public abstractions. The only new module-level symbols are: `OCR_PROMPTS` (and the aliased `OCR_PROMPT`), `_looks_like_refusal`, `_is_failed_ocr`. `_OcrPageOutcome` is runner-internal (leading underscore).
- Do NOT touch `is_illustration` semantics in any prompt or test. Pages with text on a predominantly-illustration page are still `is_illustration: true`.
- Do NOT bump `schema_version`. Stays at `1`. Additive optional fields are back-compat.
- Do NOT add CLI knobs. Retry count (`_OCR_MAX_ATTEMPTS: Final[int] = 3`), prompt list, and detection regex are module-level constants.
- Atomic-commit grouping: every file you change is part of one logical commit. The orchestrator stages them together. There must be no intermediate state where the signature of `build_text_units` is inconsistent with its callers.
- Use Google-style docstrings on every new public function and every new private function whose behavior is not obvious.
- Do NOT add `try/except` blocks except where the plan explicitly calls for them (semantic-refusal handling inside the retry loop is one explicit case).
- Tests must NOT call the real `codex` CLI, real `anyflip-downloader`, or any network. Stubs only.

## Reply format

When you exit, your final assistant message must contain exactly:

1. The list of files you created or modified (paths, one per line, with `[new]` or `[modified]` tag).
2. The top of `runner.py`: the `_OcrPageOutcome` dataclass and the new `_ocr_one_page` worker signature (just signatures + the retry-loop control structure, no bodies).
3. The full text of the `_looks_like_refusal` regex constant and the `_is_failed_ocr` body (these are load-bearing and must be readable in your reply).
4. Any deviations from the plan or this brief, with one-sentence justifications.
5. Any TODOs or follow-ups.

Do not run `git`, `uv`, `pytest`, or `ruff`. The orchestrator handles those.

## Reference files you should read in this order

1. `.omc/plans/lnvo-v2-prepare-step1.1-hardening.md` (the plan — the source of truth)
2. `automations/ln_voice_over_v2/stages/prepare/prompts.py` (current state)
3. `automations/ln_voice_over_v2/stages/prepare/ocr.py` (current state)
4. `automations/ln_voice_over_v2/stages/prepare/runner.py` (current state — the file that changes the most)
5. `automations/ln_voice_over_v2/stages/prepare/text_units.py` (current state)
6. `automations/ln_voice_over_v2/stages/prepare/contracts.py` (current state)
7. `automations/ln_voice_over_v2/common/enums.py` (`ReviewStatus` is here — DO NOT use it; the ADR justifies the `bool` choice; cited for context only)
8. `docs/lnvo/01-prepare.md` (the canonical reference page you extend)
9. Two sample cached OCR JSONs to confirm the curly-vs-straight apostrophe question (the Section A regex correctness depends on this):
   - `cat ~/.assistant/ln_voice_over_v2/projects/classroom-of-the-elite-year-2/4/source/ocr/120.json`
   - `cat ~/.assistant/ln_voice_over_v2/projects/classroom-of-the-elite-year-2/4/source/ocr/172.json`
   You may use `cat` to inspect these — they are not source-tree files, just observed model output. The regex you ship in `ocr.py` must match the apostrophe style these files use.
10. Existing tests for invariants you must not break:
    - `tests/automations/ln_voice_over_v2/stages/prepare/test_text_units.py`
    - `tests/automations/ln_voice_over_v2/stages/prepare/test_runner_resume.py`
    - `tests/automations/ln_voice_over_v2/stages/prepare/test_runner_end_to_end.py`
    - `tests/automations/ln_voice_over_v2/stages/prepare/test_validation.py`
