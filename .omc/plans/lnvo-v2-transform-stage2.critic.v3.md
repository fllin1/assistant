# Critic Review v3 — LNVO v2 Stage 2 (`transform`) Plan

Reviewer: Codex CLI (`gpt-5.5`, read-only, xhigh reasoning)
Iteration: 2 (post v1 ITERATE)
Target: `/Users/regiswoof/_workspace/projects/assistant/.omc/plans/lnvo-v2-transform-stage2.md` (v3)
Architect v3 verdict: `APPROVE`

## Verdict
`ITERATE` (two tightly-scoped slice-ordering polishes — Codex states: "After that, the plan is approve-ready.")

## v1 Must-Fix Items: Closed
- **Mid-page heading split** — RESOLVED. "Chapter Detection Strategy" §4 (plan lines 129–133).
- **`needs_review` resolution** — RESOLVED. Deterministic placeholder + hard boundaries in "Segment Creation Strategy" §2 (lines 147–151), test coverage at lines 279–282.
- **Cross-validator inside `run_transform` before write** — RESOLVED. Runner sequence at lines 231–234.
- **Ruff + pytest verification** — RESOLVED. Lines 302–308.

## New Findings (v3 only)
1. **T4 file list omits `tests/automations/ln_voice_over_v2/test_contracts.py`.** Plan notes the `_volume_index()` fixture needs `display_name="Chapter 1"` at lines 252–255, but the Slice T4 entry at line 353 doesn't list the test file. Risk: T4 commits a required-field contract change without the fixture migration, breaking the repo-wide test suite mid-stack.
2. **T1 slice-order ambiguity.** `test_chapters.py` description (lines 262–268) talks about "three `ChapterIndexEntry`s with `display_name`s" — safe only if T1 uses an internal chapter-split dataclass, not `stages/transform/contracts.py::ChapterIndexEntry`, since the latter doesn't yet have `display_name` until T4 lands.

## Slice Ordering Verdict
- T0 — Green; docs/template/AGENTS only (ruff format/check passed).
- T1 — Not proven green; T1 tests must use an internal chapter-split type, not `ChapterIndexEntry`.
- T2 — Green; tokenizer-only.
- T3 — Green if it stays on internal split/segment-building structures.
- T4 — Unsafe as written; must explicitly bundle `tests/.../test_contracts.py:241` `_volume_index()` fixture update.
- T5 — Green after T4 only; runner tests correctly depend on `VolumeIndex` with `display_name`.
- T6 — Green; docs only.

## Acceptance Criteria Audit (delta from v1)
- `test_chapters.py` — improved, but regressed on slice ordering until clarified.
- `test_quotes.py` — still good.
- `test_segments.py` — improved.
- `test_runner.py` — improved.
- `test_validators.py` — improved.

## Final Recommendation
Not ready to start T1. Make one plan amendment first: clarify T1 tests use internal chapter-split objects (not `ChapterIndexEntry`), and update Slice T4 to explicitly include `tests/automations/ln_voice_over_v2/test_contracts.py::_volume_index()` with `display_name="Chapter 1"`. After that, the plan is approve-ready.
