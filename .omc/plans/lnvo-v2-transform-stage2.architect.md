# Architect Review — LNVO v2 Stage 2 (`transform`) Plan

Reviewer: `oh-my-claudecode:architect` (Claude opus)
Target: `/Users/regiswoof/_workspace/projects/assistant/.omc/plans/lnvo-v2-transform-stage2.md`

## Verdict
`ITERATE`

## Steelman Antithesis
Strongest opposing position to **Segmentation option X + cross-page narration merging**: Stage 2 should emit page-stable segments — one narration segment per page boundary at most, never merged across pages. Under the current draft, re-running `prepare` for a single bad page (a `needs_review` retry, a fixed OCR transcript, an inserted page) can change which `text_unit_id`s belong to which segment, shifting every downstream `segment_id` whose narration straddles that page. That breaks Decision Driver #2 ("Stable IDs across reruns"). Per-page narration segments would sacrifice a small amount of narrative cohesion (Stage 3/4 has to re-join them) in exchange for monotonic stability of `seg_NNNNNN` under partial re-OCR, far simpler `source_unit_ids` (always length 1 for narration), and a cleaner round-trip invariant. The user's directive ("narration between quotes stays grouped as much as reasonably possible") admits this reading — "between quotes" can be interpreted as *within the page-local quote envelope*.

Parallel antithesis on **Chapter Detection B**: inline default regex (Q8 default) creates a hidden cross-cutting concern. Prefer profile-rule-as-only-source, with the default living in `series/contracts.py` as a `StoryProfile` default factory, so the regex is discoverable by series authors and isn't buried in `stages/transform/chapters.py`.

## Real Tradeoff Tensions

- **T1 — ID stability vs. narrative cohesion.** The plan optimizes for cohesion (cross-page narration merging) at the cost of segment-id stability under prepare reruns. The plan must commit to page-stable narration *or* spell out the contract that `seg_NNNNNN` is only stable for a given `prepared/volume.json` byte content.
- **T2 — Determinism (Q6 hard-fail coverage) vs. resilience on messy first runs.** Q6 defaults to hard-raise while Q3 defaults to silently skipping `needs_review` pages. If a `needs_review` page sits between two quote-bearing pages, union-coverage either exempts the unit silently or refuses to run. Both defaults can't be right simultaneously.
- **T3 — Heading mid-page assignment vs. content preservation.** Boundary Rule §4 says a mid-page heading starts a new chapter and the *whole* page becomes the new chapter's prefix. Pre-heading prose silently migrates to a later chapter — a provenance-principle smell. Safer rule: split the page at the heading line, attach pre-heading slice to prior chapter's last segment, post-heading to the new chapter.

## Architectural Issues to Resolve

1. **Mid-page heading rule** (Chapter Detection §4) — must split the page text, not reassign the whole page. Otherwise pre-heading prose migrates silently.
2. **Cross-validator placement / call site** — placement in `pipeline/validators.py` is correct; missing: must state it is called inside `run_transform` (mirroring `validate_prepared_volume` in `run_prepare`).
3. **`runner.py` shape drift** — confirm no `Callable` seam kwargs (no external CLI/network). `--force` semantics mirror prepare's `shutil.rmtree`.
4. **`validation.py` split** — be explicit: stage-local validation = artifact-internal invariants; `pipeline/validators.py` cross-validator = round-trip against `prepared/volume.json`.
5. **Stage-3 creep risk in quote heuristics** — call out that single-quote paragraph-start rule is the structural-only line; em-dash dialogue (Q5) and sentence splitting belong to Stage 3+.
6. **Doc-update list is incomplete** — add `automations/ln_voice_over_v2/AGENTS.md` (B1 widening), `automations/ln_voice_over_v2/README.md` (CLI usage), and re-confirm `seg_NNNNNN` 1-indexed in `docs/lnvo/contracts-index.md`.
7. **Q1/Q7 must be promoted from "Blocker" to "Decided"** — `unit_NNNNNN` is 0-indexed (per `stages/prepare/text_units.py:34`); `seg_NNNNNN` is 1-indexed. Lock both in the ADR.
8. **`__init__.py` missing from explicit module list** — mirror prepare exactly.

## Synthesis
Single most-valuable change: introduce a **"Stability Contract" subsection** that resolves T1 + T3 together. Keep cross-page narration merging *but* require that the cross-validator (Q6 hard-raise) treat a `needs_review` page as a hard gate: if any `text_unit` in the chapter is `needs_review`, transform refuses to merge narration across that gap and instead emits page-local narration segments for the affected window with `parser_hints.needs_review_boundary: true`. Pair with the mid-page heading split fix.

## Principle Violations
- **Stable IDs (Driver #2):** cross-page narration merging weakens reproducibility under partial prepare reruns — medium severity, undocumented.
- **Provenance mandatory:** mid-page heading rule risks silent migration of pre-heading prose — medium severity.
- Determinism, structural-hints-only, contracts-authoritative, no-artifact-sprawl: clean.

## Key References
- `.omc/plans/lnvo-v2-transform-stage2.md` §"Chapter Detection Strategy" §4 — mid-page rule
- `.omc/plans/lnvo-v2-transform-stage2.md` §"Segment Creation Strategy" §4 — cross-page narration merging
- `automations/ln_voice_over_v2/stages/prepare/runner.py:140` — pattern: cross-validator called inside `run_prepare`
- `automations/ln_voice_over_v2/stages/prepare/text_units.py:34` — 0-indexed `unit_NNNNNN` source of truth
- `automations/ln_voice_over_v2/pipeline/validators.py:16` — mirror target for `validate_transform_against_prepared`
- `automations/ln_voice_over_v2/AGENTS.md:25` — runner/CLI restriction widening required by B1
