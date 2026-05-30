# Critic Review — LNVO v2 Stage 2 (`transform`) Plan

Reviewer: Codex CLI (`gpt-5.5`, read-only, xhigh reasoning)
Target: `/Users/regiswoof/_workspace/projects/assistant/.omc/plans/lnvo-v2-transform-stage2.md`
Architect input also visible: `.omc/plans/lnvo-v2-transform-stage2.architect.md`

## Verdict
`ITERATE`

## Strengths
- Cleanly honors the Stage 2 boundary: deterministic transform only, no LLM/OCR/dialogue/scene ownership.
- Correctly uses `parser_hints.quote_candidate` without adding public `Segment` fields; `parser_hints` is already `dict[str, Any]` in `stages/transform/contracts.py:37`.
- Options B and X match the user direction better than hardcoded/manual chaptering or sentence/paragraph segmentation.
- Validator intent is strong: ID density, path shape, chapter/file agreement, and `source_unit_ids` coverage are all named.

## Findings (must-fix)
1. **Chapter Detection Strategy.** The mid-page heading rule is wrong. It assigns the entire page to the new chapter and makes pre-heading prose "a narration prefix of the new chapter" (`.omc/plans/lnvo-v2-transform-stage2.md:81`), which violates provenance and chapter semantics. Fix by splitting page text at the heading: pre-heading text stays with the prior chapter, heading/post-heading text starts the new chapter; update `test_chapters.py` accordingly.
2. **Segment Creation Strategy / Blockers Q3+Q6.** The plan conflicts with itself on `needs_review`: skip empty/`needs_review` units (line 91, Q3 default line 247) while claiming hard coverage (line 147, Q6 default line 250). Prepare explicitly emits empty sentinel transcripts with `needs_review: true` (`docs/lnvo/01-prepare.md:70-72`). Fix by deciding one behavior before implementation — preferably hard-fail transform on any `needs_review` unit or emit an explicit non-empty placeholder segment.
3. **Validation / Runner + CLI Shape.** The cross-validator is planned but not required in `run_transform`. Adding `validate_transform_against_prepared` (lines 154–155) is insufficient unless the runner calls it before writes, mirroring prepare's validate-before-save pattern (`stages/prepare/runner.py:140-141`). Fix the runner spec and tests to require that call.
4. **Tests / Verification command.** `pytest tests/automations/ln_voice_over_v2/` alone (lines 211–214) is not sufficient completion evidence. Project rules require Ruff formatting/linting plus pytest. Fix verification to include `ruff format --check .`, `ruff check .`, and the pytest command.

## Findings (should-improve)
1. **RALPLAN-DR Summary.** Option Y is partly straw-manned: sentence segmentation does not "push work onto Stages 3/4" as stated (line 39); the real rejection is that it over-fragments Stage 2 and violates quote-boundary grouping. Fix the rationale.
2. **Doc Updates.** The plan says no `contracts-index` changes (line 224), but the index still shows segment shape as `seg_000000` (`docs/lnvo/contracts-index.md:22`) while the plan requires 1-indexed `seg_000001` starts. Clarify whether the index is only a regex example or update it.
3. **Runner + CLI Shape.** Option B depends on `StoryProfile.rules.chapter_headings`, but the runner does not specify how `<series>/config/story_profile.json` is loaded, despite being a Stage 2 input (`docs/lnvo/02-transform.md:14-17`). Add the load path and accepted rule shape.

## Acceptance Criteria Audit
- `test_chapters.py`: Needs sharpening; must assert split-at-heading behavior, not whole-page reassignment.
- `test_quotes.py`: Mostly testable, but page-boundary `source_unit_ids` belongs in segmentation, not tokenizer-only tests.
- `test_segments.py`: Needs sharpening; assert exact text, exact `source_unit_ids`, and exact `parser_hints`.
- `test_runner.py`: Needs sharpening; require validator invocation before write and exact emitted paths/files.
- `test_validators.py`: Testable as written, but add duplicate/gapped `order` and bad `segments_file` path cases.

## Final Recommendation
Minimum delta to approve: fix the mid-page split rule, resolve `needs_review` behavior, require `run_transform` to call the new cross-validator, sharpen the five test specs, and expand verification to Ruff plus pytest. I agree with the Architect on the mid-page and validator-call issues; the added blocker here is that the current test plan would let those defects slip through.
