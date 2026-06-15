# Handoff: LNVO v2 dialogue chunking for oversized chapters

> Self-contained brief for a **fresh session** (or post-compaction planner) to design
> and implement chunking for the Stage 3 dialogue attribution. Everything below was
> discovered in the session that fixed the timeout; read this first, then plan.

## Why this work exists (the real problem)

Stage 3 makes **one `codex` attribution call per chapter**. After raising the per-chapter
timeout to 600s (see Baseline below), a real whole-volume run on
`classroom-of-the-elite-year-2 / volume 4` produced `4 written, 5 skipped, 0 failed` —
**no timeouts** — but exposed a *different, distinct* failure on the largest chapter:

| Chapter | candidates | dialogues | rejected | narrator | outcome |
| --- | --- | --- | --- | --- | --- |
| chapter_07 | ~707 | 675 | 32 | None | ✅ usable |
| **chapter_06** | **733** | **0** | **733 (all `model_omitted`)** | None | ❌ **degenerate** |

chapter_06's model returned valid JSON **in time**, but with an empty decision set and this
review note:

> "Unable to return a complete strict attribution set within this response because the
> payload contains several hundred candidate segments and requires one decision per
> candidate segment."

So this is an **output-completeness limit, NOT a timeout**. The model declines to emit
~733 per-candidate decisions in a single response. Observed threshold: ~707 candidates OK,
733 fails. The runner's trust boundary handled it safely (no corruption; flagged
`needs_review`; every candidate → `model_omitted`), but the chapter has zero usable output.

**Chunking is the fix:** split an oversized chapter into windows, attribute each in its own
`codex` call, then merge the partial proposals before the existing assembly step.

### Keep three distinct issues separate — do not conflate
1. **Timeout** (wall-clock) — already fixed (configurable, default 600s).
2. **Response completeness** (too many candidates per single response) — *this work*.
3. **Narrator detection** — `narrator=None` on chapters 05/06/07 is the pre-existing
   known issue #2 (`narrator_hint` is in the payload but `DIALOGUE_PROMPT` never tells the
   model to use it). Independent of chunking, but chunking makes it worse (see below).

## Baseline state (what's already in the tree)

Branch `feat/lnvo-v2-dialogue-stage3`. The timeout fix is **implemented, codex-critic
approved, 196 tests green, but UNCOMMITTED** — 8 modified files:
`stages/dialogue/{agent.py,runner.py,__main__.py}`,
`tests/.../dialogue/{test_agent,test_runner,test_main}.py`, `docs/lnvo/{03-dialogue,runbook}.md`.
What it added: `agent.DEFAULT_DIALOGUE_TIMEOUT_SECONDS=600`; `timeout_seconds` on
`DialogueConfig`/`DialogueVolumeConfig` + `--timeout` CLI flag; `run_codex_dialogue` raises
both subprocess errors `from None` (so the prompt never leaks via `__cause__.cmd`).
**Recommended first step of the new session: commit this baseline before starting chunking.**

## Current architecture & the seams chunking plugs into

Path: `automations/ln_voice_over_v2/stages/dialogue/`

- `context.py::build_chapter_payload(segment_file, story_profile) -> ChapterPayload`
  — `ChapterPayload` carries `segments` (EVERY segment, each tagged role `candidate`|`narration`),
  `candidate_ids` (only `parser_hints.quote_candidate is True`), and `narrator_hint`.
  `select_candidates()` is the candidate filter. **The payload deliberately includes narration
  so the model has turn-taking context — any chunker MUST preserve narration context around
  each candidate, i.e. split by segment windows, not by candidate id alone.**
- `prompts.py::build_prompt(payload, roster) -> str` — wraps payload JSON + roster.
- `agent.py::run_codex_dialogue(prompt, *, timeout_seconds=600) -> DialogueProposal`
  — one codex subprocess; `DialogueProposal = {decisions[], narrator_raw, review_notes[]}`.
- `runner.py::run_dialogue(config, *, attribute_fn=None)` — the orchestrator:
  builds payload → `proposal = attribute_fn(payload)` → **assembles the trusted
  `DialogueChapter`**: iterates `candidate_ids`, `decision_by_id` lookup, candidates the model
  omitted become `RejectedCandidate(reason="model_omitted")`, canonicalizes speakers + narrator,
  computes `review_required`, sorts by segment order, runs BOTH validators, writes.
  The injectable seam is `attribute_fn: Callable[[ChapterPayload], DialogueProposal]`
  (default closure calls `run_codex_dialogue(build_prompt(...), timeout_seconds=config.timeout_seconds)`).

**Cleanest injection point:** keep the existing assembly untouched and insert a split→N-calls→merge
layer that still returns ONE `DialogueProposal` to `run_dialogue`. I.e. a new
`chunking.py` with pure, unit-testable `split_payload(payload, ...) -> list[ChapterPayload]`
and `merge_proposals(list[DialogueProposal]) -> DialogueProposal`, wired so the default
`attribute_fn` chunks when `len(candidate_ids)` exceeds a threshold and calls the model per chunk.
This keeps the codex call behind the seam (tests inject a fake attribute/model and never spawn codex).

## Design decisions the planner must resolve

1. **When to chunk.** Recommend: only when `len(candidate_ids) > THRESHOLD` (e.g. ~250–400,
   safely under the observed ~707 ceiling) — small/medium chapters keep the single-call path,
   preserving whole-chapter narrator context for the common case.
2. **How to split.** By segment windows that bound *candidate count per chunk* while carrying
   the surrounding narration. Decide overlap: none (clean partition of candidates) vs small
   overlap (better local context, but creates duplicate decisions — see #4).
3. **Narrator merge.** Each chunk proposes its own `narrator_raw`. Pick a rule (first non-null /
   majority vote). Whole-chapter narrator signal is weakened by chunking — strongly consider
   fixing **known issue #2** (make `DIALOGUE_PROMPT` actually consume `narrator_hint`) and/or a
   cheap dedicated narrator pass, so each chunk is seeded with the chapter narrator.
4. **Duplicate decisions across chunks.** Today two decisions for one candidate silently
   last-wins (**known issue #1**, `runner.decision_by_id`). Chunk overlap makes collisions
   likely → the merge step should detect conflicts and flag them for review rather than
   silently dropping. Consider fixing #1 as part of this.
5. **review_notes** — concatenate + dedupe across chunks.
6. **Where the code lives** — new `stages/dialogue/chunking.py`; keep `run_dialogue`’s assembly
   as the single trust boundary that consumes the merged proposal.

## Verification (acceptance)

- **Real-data acceptance:** re-run chapter_06 (733 candidates) with `--force` and confirm it now
  yields substantial real `dialogues` (not 733 `model_omitted`). Command:
  `python -m automations.ln_voice_over_v2.stages.dialogue --series classroom-of-the-elite-year-2 --volume 4 --chapter chapter_06 --force`
  (artifacts live at `~/.assistant/ln_voice_over_v2/projects/classroom-of-the-elite-year-2/4/dialogue/`).
- **No regression:** chapter_07 (~707, currently works) must stay healthy.
- **Unit tests (no codex):** `split_payload` (window boundaries, candidate-count caps, narration
  retained) and `merge_proposals` (union of decisions, narrator merge rule, review_notes dedupe,
  duplicate-conflict handling) are pure functions — test them deterministically. Keep the model
  call behind the `attribute_fn` seam.
- Gate: `ruff check` + `ruff format --check` + `pytest tests/automations/ln_voice_over_v2`.

## Gotchas (carried over)

- **codex `ruff --fix` PostToolUse hook strips a just-added import** when its first use lands in
  a *later* edit. Add the import AND its first usage in the SAME edit, or re-add after.
- Stage 3 is **non-deterministic**; idempotency = skip-existing + `--force`. The dialogue JSON is
  the working review file; validate-before-write protects existing good files.
- `codex exec` sometimes ends a turn narrating intent without applying patches — re-run/resume and
  verify with `ruff` + `pytest` yourself.

## Reference set to read first (new session)

`docs/lnvo/03-dialogue.md` (contract + Implementation Notes + Debugging & Known Issues),
`docs/lnvo/runbook.md` (Stage 3 commands), `.omc/plans/lnvo-v2-dialogue-stage3.md` (original
consensus plan), and this file. Memory: `project_lnvo_dialogue_stage3_status`.
