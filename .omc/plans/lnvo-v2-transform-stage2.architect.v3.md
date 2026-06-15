# Architect Review v3 — LNVO v2 Stage 2 (`transform`) Plan

Reviewer: `oh-my-claudecode:architect` (Claude opus)
Iteration: 2 (post v1 ITERATE)
Target: `/Users/regiswoof/_workspace/projects/assistant/.omc/plans/lnvo-v2-transform-stage2.md` (v3)

## Verdict
`APPROVE`

## How v1 Findings Resolved in v3
1. **Mid-page heading rule** — RESOLVED. "Chapter Detection Strategy" §4 splits the page at the heading line; same `text_unit_id` appears in both neighbours' `source_unit_ids`.
2. **Cross-validator call site** — RESOLVED. Validator runs inside `run_transform` before any write, mirroring `prepare/runner.py:140-141`.
3. **Runner shape drift / no Callable seam** — RESOLVED. "Runner + CLI Shape" forbids `Callable` seam kwargs, network, subprocess; `--force` mirrors prepare's `shutil.rmtree`.
4. **`validation.py` split** — RESOLVED. Stage-local (artifact-internal) vs `pipeline/validators.py` (round-trip) are separate subsections.
5. **Stage-3 creep risk** — RESOLVED. Single-quote-opener heuristic tagged as "structural-only line"; em-dash explicitly deferred.
6. **Doc-update list completeness** — RESOLVED. All docs + template + AGENTS.md listed.
7. **Q1/Q7 promotion** — RESOLVED. Locked in "Outputs" + ADR "Locked decisions".
8. **`__init__.py` in module list** — RESOLVED. Listed under "Scope".
9. **Q3↔Q6 conflict** — RESOLVED via `needs_review` placeholder segment.
10. **Ruff+pytest verification** — RESOLVED.

## New v3 Risks
1. **`display_name` required contract addition.** Existing `_volume_index()` fixture at `test_contracts.py:241` will break the instant T4 lands. Plan bundles the fixture update inside T4 — safe if Codex actually includes that line.
2. **Template-vs-override resolution is input #2 to ID stability.** Editing the per-series override renumbers `segment_id`s. Operational risk only; plan flags it in Stability Contract consequences.
3. **Disambiguation Protocol is a project-wide rule introduced in a stage plan.** Minor scope-creep concern; AGENTS.md is the right home.

## Slice Ordering Audit
- **T0 (done):** docs + template + AGENTS.md only. Clean.
- **T1–T3:** pure-function modules with their own tests. They emit `display_name` as a Python string internally, NOT as a Pydantic field — `ChapterIndexEntry` is not yet modified. Safe **provided** T1–T3 tests do not transitively instantiate `ChapterIndexEntry`.
- **T4 (contract + validators):** lands `display_name` on `ChapterIndexEntry` AND updates `_volume_index()` fixture. Only slice where repo-wide tests would fail without that bundle. Safe.
- **T5 (runner + CLI + e2e):** depends on T1–T4. Correctly placed last among code slices.
- **T6 (README + contracts-index):** docs polish.

## Final Note
Green light for Codex Critic. v3 cleanly resolves every v1 finding, locked user decisions are reflected in body and ADR, slice ordering keeps each intermediate commit green provided T4 bundles the fixture update. Critic should sanity-check that T1–T3 tests do not transitively instantiate `ChapterIndexEntry`.

## Key References
- `.omc/plans/lnvo-v2-transform-stage2.md` — v3 plan
- `automations/ln_voice_over_v2/stages/transform/contracts.py` — `ChapterIndexEntry` lacks `display_name` (T4 target)
- `automations/ln_voice_over_v2/stages/prepare/runner.py:140-141` — validator-before-save pattern T5 mirrors
- `tests/automations/ln_voice_over_v2/test_contracts.py:241` — `_volume_index()` fixture T4 must update
