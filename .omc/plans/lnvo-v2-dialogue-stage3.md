# LNVO v2 — Stage 3 `dialogue` Implementation Plan

Status: **APPROVED FOR EXECUTION** (user 2026-05-30). Alias-resolution blocker resolved via **R1** — add additive `CharacterRegistry.resolve()` to `series/contracts.py` (sanctioned series-contract change). Implementation delegated to Codex agents, slices D0–D7.
Mode: ralplan (consensus, short mode). Implementation delegated to Codex agents.
Scope: `automations/ln_voice_over_v2/stages/dialogue/` + tests + docs. No `src/assistant/` changes.

---

## 1. Context & Current State

The Stage 3 **contract layer already exists** and must NOT be rebuilt:

- `stages/dialogue/contracts.py` — `DialogueChapter`, `Perspective`, `DialogueRow`, `RejectedCandidate` (strict, `extra="forbid"`, frozen).
- `pipeline/validators.py::validate_dialogue_against_segments(dialogue, segments, registry)` — already enforces: chapter id match, every `segment_id` resolves, no duplicate dialogue segment, speaker canonical-or-`Unknown`, detected narrator canonical-or-`null`.
- `docs/lnvo/03-dialogue.md` — the published contract page.
- `common/paths.py::dialogue_chapter_path(...)` → `<volume>/dialogue/<chapter_id>.json`.
- `series/contracts.py::CharacterRegistry` (`has_character(name)`), `Character(name, aliases, ...)`.
- `common/enums.py` — `ReviewStatus{accepted, needs_review}`, `PerspectiveStatus{unset, detected}`, `ArtifactKind.DIALOGUE_CHAPTER`.

**One sanctioned additive contract change (user-approved 2026-05-30):** add `CharacterRegistry.resolve(name) -> str | None` (exact name + alias lookup, no fuzzy) to `series/contracts.py`. This is additive (new method; no key/shape/enum change) and was explicitly confirmed per package `AGENTS.md:29`. No other contract change is permitted; any further gap must be raised, not silently made.

The established **model-call boundary pattern** is `stages/prepare/ocr.py::run_codex_ocr`:
`subprocess.run(["codex","exec","-i",img,"-m",model,"--ephemeral","--skip-git-repo-check","--ignore-user-config","-s","read-only",prompt])`, strict `model_validate_json` of stdout, `RuntimeError` on non-zero exit, `ContractValidationError` on malformed JSON. The prepare runner injects the boundary as an optional `ocr_fn` seam so tests never spawn `codex`. Stage 3 mirrors both the subprocess shape and the seam.

What is **missing** (this plan):
runner, CLI, LLM boundary (`agent.py` + `prompts.py`), context-window builder, name normalizer, `characters.json` loader (+ path helper), stage-local validation, and tests.

---

## 2. RALPLAN-DR Summary

### Principles (load-bearing)
1. **Deterministic contract around a replaceable model call.** Everything except the single model call is pure/testable; the model boundary is one injectable function returning strict JSON, validated before any write.
2. **The model proposes; the runner decides.** The LLM never emits the persisted `DialogueChapter`. It returns an internal `DialogueProposal`; the runner canonicalizes names, computes status, and assembles the trusted artifact.
3. **Never invent characters.** Unresolved speaker → `"Unknown"`; unresolved narrator → `null` + review flag. Canonical names/aliases come only from `characters.json`.
4. **The dialogue JSON is the working review file.** Do not clobber human edits: skip if the file exists unless `--force`. Validate-before-write so a bad run never corrupts an existing good file.
5. **Match Stage 1/2 conventions exactly.** Same runner/CLI/validation/test shapes; reuse existing helpers (`json_io`, `paths`, `resolve_story_profile_path`, the cross-validator).

### Decision Drivers (top 3)
- **Trust boundary integrity** — model output must be untrusted and fully validated.
- **Reviewer safety** — re-runs must not destroy human review edits.
- **Consistency & low surface area** — reuse existing contracts/validators/patterns; add only what each stage needs (package `AGENTS.md`).

### Viable Options for the Main Decision (model invocation granularity)

**Option A — One structured call per chapter (RECOMMENDED).**
Pass the chapter's segments (candidates + surrounding narration as context) in one prompt; model returns one JSON: per-candidate accept/reject + speaker + reason, plus chapter narrator/perspective. Runner validates and assembles.
- Pros: simplest deterministic contract around a single call; whole-chapter context is exactly what narrator/perspective resolution needs; one artifact, one validation; cheapest orchestration; mirrors "one strict JSON validated before writing."
- Cons: one malformed response fails the whole chapter (acceptable — validate-before-write leaves prior file intact); very long chapters could strain context (mitigation: log candidate/segment counts; chunking is a documented follow-up, not v1).

**Option B — One call per candidate + a separate perspective pass.**
- Pros: per-item failure isolation; smaller prompts.
- Cons: N+1 subprocess calls per chapter (slow, more failure surface); per-candidate calls lack whole-chapter view; narrator pass still needs chapter context anyway; more orchestration code. Heavier without clear v1 benefit.

**Invalidation of B for v1:** light-novel chapters are short enough that the whole chapter fits one call; B's only real advantage (failure isolation) is already covered by validate-before-write + `--force` re-run. B is recorded as the scale-up path if real chapters exceed a single-call budget.

### Acceptance Criteria (testable)
- `python -m automations.ln_voice_over_v2.stages.dialogue --series S --volume V --chapter chapter_07_1` writes a `dialogue/chapter_07_1.json` that round-trips as `DialogueChapter` and passes both stage-local and cross validators.
- Re-running without `--force` on an existing file does not overwrite it (exit 0, logged skip); `--force` regenerates.
- A missing `characters.json` fails clearly before any model call.
- `ruff format . && ruff check . && pytest tests/automations/ln_voice_over_v2/stages/dialogue` all green.
- The nine spec test cases (Section 6) pass.

---

## 3. Target Module Layout

```
automations/ln_voice_over_v2/
  common/paths.py                      # + characters_config_path(data_root, series)
  stages/dialogue/
    __init__.py                        # exists
    contracts.py                       # exists — unchanged
    config.py        (new)             # load_character_registry(); story_profile reuse
    context.py       (new)             # candidate selection + context windows (pure)
    names.py         (new)             # alias→canonical / Unknown / narrator resolution (pure)
    prompts.py       (new)             # dialogue attribution prompt(s)
    agent.py         (new)             # DialogueProposal model + run_codex_dialogue() boundary
    validation.py    (new)             # stage-local artifact invariants
    runner.py        (new)             # orchestration, injectable attribute_fn seam
    __main__.py      (new)             # CLI, mirrors transform/__main__.py
tests/automations/ln_voice_over_v2/stages/dialogue/
    __init__.py, test_config.py, test_context.py, test_names.py,
    test_agent.py, test_validation.py, test_runner.py
docs/lnvo/03-dialogue.md               # add Implementation Notes + Design History
```

---

## 4. Design Decisions

### 4.1 Model boundary (`agent.py`)
- Internal **`DialogueProposal`** strict Pydantic model (`extra="forbid"`), the ONLY thing the model emits:
  ```
  DialogueProposal:
    decisions: tuple[CandidateDecision, ...]
    narrator_raw: str | None
    review_notes: tuple[str, ...] = ()
  CandidateDecision:
    segment_id: SegmentId
    is_dialogue: bool
    speaker_raw: str | None       # free-text name as the model sees it; "" / null allowed
    reason: str = ""              # required-by-runner for rejects
  ```
- **`run_codex_dialogue(payload, *, model, executable="codex", timeout_seconds, prompt) -> DialogueProposal`** — subprocess shape copied from `run_codex_ocr` (`--ephemeral`, `--skip-git-repo-check`, `--ignore-user-config`, `-s read-only`), strict JSON parse, `RuntimeError` on non-zero exit, `ContractValidationError` on malformed.
  **Payload delivery (D3 — was under-specified; resolved):** there is NO image, so the OCR `-i <image>` flag is **dropped entirely** (no dangling `-i`). The serialized chapter payload JSON is appended to the instruction prompt and passed as the final positional `prompt` argv element (same slot OCR uses for its prompt). The D3 "exact argv" test asserts this shape (no `-i`, payload-bearing final arg).
- The runner accepts `attribute_fn: Callable[[ChapterPayload], DialogueProposal] | None` (the seam). Tests inject a fake; runtime builds the default from config.

### 4.2 Context windows (`context.py`, pure)
- `select_candidates(segment_file)` → candidates where `parser_hints.get("quote_candidate") is True`.
- `build_chapter_payload(segment_file, story_profile_hints)` → a strict, serializable payload: ordered segments with `segment_id`, `text`, `quote_candidate`, and a `role` tag (`candidate`/`narration`), plus optional narrator hint from `story_profile.rules`. Window = each candidate plus its nearest preceding/following narration segments and nearby dialogue (configurable radius, default small). Never rewrites segment text.

### 4.3 Name normalization (`names.py`, pure)
> ⚠ **BLOCKER corrected from consensus (see §10.5).** v2 `CharacterRegistry` (`series/contracts.py:32-40`) exposes ONLY `has_character(name)` — exact `==` on `Character.name`, **no alias resolution and no fuzzy match**. v1's `find`/`fuzzy_find`/`_canonicalise_*` (`automations/ln_voice_over/models.py:131-190`, `review.py:160-162`) **do not exist in v2** and cannot be "ported." Alias→canonical (test cases 4, 6) therefore has no backing code today. Resolution mechanism is an **open decision for the user** (§10.5).
- `canonical_speaker(raw, registry) -> str`: trimmed exact match to a `Character.name` → that name; match to any `Character.aliases` entry → that character's canonical name; empty/None/unmatched → `"Unknown"`. Never invents. **Exact name+alias only — NO fuzzy matching in v1** (v1's `fuzzy_find` + raw-passthrough are intentionally dropped; fuzzy is a follow-up).
- `canonical_narrator(raw, registry) -> str | None`: same resolution; unresolved/None → `None`.
- **First-person/POV rule:** a first-person speaker tag (`"I"`/`"me"`/equivalent) resolves through the *resolved chapter narrator* to that narrator's canonical name (the "POV character is the narrator" rule). Narration is not a dialogue row, so `"Narrator"` is NOT emitted as a speaker here.
- `UNKNOWN_SPEAKER` is **imported from `pipeline/validators.py`** (single source) — do NOT redefine it in `names.py`.

### 4.4 Runner assembly & review logic (`runner.py`)
- Load `volume_index.json`; confirm `--chapter` is a member; resolve its `segments_file`; load the `SegmentFile`; load `CharacterRegistry` (required); resolve+load `story_profile` (optional, reuse `transform.chapters.resolve_story_profile_path`/`load_story_profile`).
- If `dialogue/<chapter>.json` exists and not `--force`: log skip, return (protect the review file). With `--force`: regenerate.
- Build payload → `attribute_fn(payload)` → `DialogueProposal`.
- Assemble (rows built in **segment order**, not model output order, for clean diffs):
  - **Stray ids** — a proposal `segment_id` NOT in the candidate set is rejected outright (model must not classify non-candidates): emit `RejectedCandidate(segment_id, reason="model_stray_segment")` only if it resolves to a real segment; otherwise drop it and add a `review_note`. (Cross-validator still guards segment existence.)
  - **Omitted candidates** — a candidate the model returned NO decision for becomes an explicit `RejectedCandidate(segment_id, reason="model_omitted")` (NOT a silent soft-flag). This makes §4.5 coverage a real hard gate.
  - accepted (`is_dialogue=True`) → `DialogueRow(segment_id, speaker=canonical_speaker(...))`; rejected → `RejectedCandidate(segment_id, reason)`. Narrator → `canonical_narrator(...)`; `perspective.status = detected` if narrator resolved else `unset` with `narrator=null`.
- **`review_required`** (computed from the **canonicalized** speakers, not raw proposal) = any accepted speaker is `"Unknown"` OR perspective unresolved OR any candidate was omitted/stray OR model `review_notes` non-empty. **`status`** = `needs_review` if `review_required` else `accepted`. (An all-narration chapter with zero candidates is valid: `review_required=False`, `status=accepted`.)
- `validate_dialogue_artifact(...)` (stage-local) AND `validate_dialogue_against_segments(...)` (cross) run BEFORE write (mirror transform: bad run leaves existing file untouched). Write via `save_json_contract`.

### 4.5 Stage-local validation (`validation.py`) — only checks the cross-validator does NOT cover
- **Coverage**: every candidate `segment_id` appears in exactly one of `dialogues` / `rejected_candidates` (no candidate silently dropped).
- **Disjoint**: `dialogues` and `rejected_candidates` share no `segment_id`.
- **Status consistency**: `status == needs_review` iff `review_required is True`.
- (Segment-resolution, duplicate-dialogue, speaker/narrator canonicality are delegated to `validate_dialogue_against_segments`.)

### 4.6 `characters.json` loading (`paths.py` + series-shared loader)
- `paths.characters_config_path(data_root, series)` → `<data_root>/<series>/config/characters.json` (NEW; sits beside `story_profile.json`, in `common/paths.py` next to `dialogue_chapter_path`).
- **Loader placement (consensus correction):** `load_character_registry(path) -> CharacterRegistry` is **series-shared, not dialogue-private** (Stage 4 scenes and Stage 5 generation also need the registry). Put it in a series-level module (e.g. `series/loader.py` or `common/series_config.py`) alongside `CharacterRegistry`, via `load_json_contract`. `dialogue/config.py` is a thin consumer that re-exports/calls it — no second copy in another stage later.
- **No packaged fallback** (character lists are series content, not a default): a missing file raises a clear `ContractValidationError`/`FileNotFoundError` BEFORE any model call.

### 4.7 CLI (`__main__.py`) — mirror `transform/__main__.py`
`--series --volume --chapter [--data-root --force]`. Same logging setup, same `ContractValidationError`→exit 2 / generic→exit 1 / success→print path + exit 0. Batch-all-chapters is a documented follow-up.

### 4.8 Non-determinism & copyright framing
Stage 3 is NOT byte-deterministic (LLM). Idempotency is provided by skip-existing + validate-before-write, not reproducibility. The prompt frames attribution as a mechanical structured task and uses `--ignore-user-config` (same refusal mitigations as OCR); a single prompt for v1, with the prepare-style prompt-escalation list noted as a follow-up if refusals appear on real volumes.

---

## 5. Codex-Agent Slices (ordered; each = one bounded task)

Each slice: **objective / allowed scope / inputs / output / verification (`ruff` + targeted `pytest`) / stop condition (tests green, in-scope files only).**

- **D0 — Config seam.** `paths.characters_config_path` + `dialogue/config.py` (`load_character_registry`, story_profile reuse). Tests: load valid registry; missing file raises before any model call.
- **D1 — Context windows.** `dialogue/context.py` (pure): candidate selection by `quote_candidate`, payload/window construction, no text rewrite. Tests: selection, window includes prev/next narration.
- **D0b — Registry resolver (sanctioned contract change).** Add `CharacterRegistry.resolve(name) -> str | None` to `series/contracts.py` (exact name + alias, no fuzzy). Update `docs/lnvo/00-series-parameters.md`/contracts-index if it documents the registry. Tests: name match; alias match; miss→`None`. Must land before D2.
- **D2 — Name normalization.** `dialogue/names.py` (pure), thin wrapper over `CharacterRegistry.resolve` (D0b). Exact name+alias only, no fuzzy. Tests: alias→canonical; unknown→`Unknown`; first-person→narrator's canonical name; narrator unresolved→`None`.
- **D3 — Model boundary.** `dialogue/prompts.py` + `dialogue/agent.py` (`DialogueProposal`, `run_codex_dialogue`). Tests (monkeypatch `subprocess.run`, mirror `test_ocr_function.py`): exact argv; strict stdout parse; malformed→`ContractValidationError`; non-zero exit→`RuntimeError`.
- **D4 — Stage-local validation.** `dialogue/validation.py` (coverage, disjoint, status consistency). Tests for each invariant.
- **D5 — Runner.** `dialogue/runner.py` with injectable `attribute_fn`. Tests (fake seam): valid file; rejected candidate; unknown speaker; alias normalization; invalid segment reference raises; unresolved narrator → `review_required`/`needs_review`; skip-existing vs `--force`.
- **D6 — CLI.** `dialogue/__main__.py`. Light test: arg parse + exit codes via injected seam or `ContractValidationError` path.
- **D7 — Docs.** `docs/lnvo/03-dialogue.md` Implementation Notes (model boundary, skip-existing, status rule, characters.json required) + Design History entry. Touch `runbook.md`/`README` only if a user-facing command line changes; CONTEXT.md only if vocabulary changes (not expected).

Dependency order: D0,D1,D2 parallel-safe → D3 → D4 → D5 → D6 → D7. Commit per slice after `ruff` + `pytest` green (project `AGENTS.md` commit discipline; automations need no GitHub issue).

---

## 6. Test Matrix (the nine required cases → slice)
1. valid dialogue file → D5
2. rejected quote candidate → D5
3. unknown speaker → D2 + D5
4. alias normalization → D2 + D5
5. invalid segment reference → D5 (cross-validator raises)
6. unresolved narrator marks review needed → D2 + D5
7. (added) missing `characters.json` errors before model call → D0
8. (added) skip-existing protects review file; `--force` regenerates → D5
9. (added) candidate coverage / disjoint / status-consistency invariants → D4
10. (added) unknown `--chapter` fails before any model call → D5/D6
11. (added) `review_required` computed from canonicalized speakers (not raw proposal) → D5
12. (added) omitted candidate → explicit `RejectedCandidate(reason="model_omitted")` → D5

---

## 7. Risks & Mitigations
- **Clobbering human review edits** → skip-existing-unless-`--force`; validate-before-write.
- **Model invents a character / mislabels** → canonicalize to `Unknown`/`null` + `review_required`; reviewer fixes the working file.
- **Malformed model JSON** → strict parse → `ContractValidationError`; existing file untouched.
- **Codex refusal on copyrighted excerpts** → mechanical framing + `--ignore-user-config`; escalation-prompt list is a ready follow-up.
- **Large chapters strain a single call** → log counts; Option B / chunking documented as scale-up.
- **Scope creep into contracts** → contracts frozen; any gap is raised for user confirmation, not silently changed.

## 8. Out of Scope
Narration adaptation (Stage 4), voice mapping/generation (Stage 5), batch-all-chapters CLI, response caching, multi-volume sampling, any `src/assistant/` change.

---

## 9. ADR (to finalize after consensus)
- **Decision:** _pending_ (recommend Option A — one structured per-chapter call).
- **Drivers:** trust-boundary integrity, reviewer safety, consistency/low surface area.
- **Alternatives considered:** Option B (per-candidate) — deferred as scale-up.
- **Consequences:** non-deterministic stage; idempotency via skip-existing; new `characters.json` hard dependency.
- **Follow-ups:** batch-all CLI; prompt escalation; chunking for large chapters.

---

## 10. Consensus Review

> Process note: one Opus Architect pass and two Sonnet Critic passes ran as separate read-only agents against this plan and the real codebase and returned in full (earlier launches that appeared to stall did complete). Their findings are summarized below; the inline analytical lanes are retained as the synthesis. The refinements in §10.3 + §10.6 are **authoritative addenda** and override anything earlier in this plan that conflicts. The blocker in §10.5 is an **open decision the user must make** before D2 implementation (it concerns a frozen series contract).

### 10.1 Architect lane — steelman antithesis + synthesis
**Antithesis (strongest case against the central design):** A single per-chapter call couples two distinct tasks — per-candidate accept/reject/attribute and whole-chapter narrator/perspective resolution — so one malformed or partial response fails the entire chapter and discards all correct per-candidate work. Attribution quality also degrades as candidate count grows (attention dilution), exactly where it is hardest. The internal `DialogueProposal` layer can look like throwaway ceremony versus having the model emit `DialogueRow`-shaped rows directly and letting the existing cross-validator reject bad names.

**Rebuttal / synthesis:** `DialogueProposal` is **the trust boundary, not ceremony**. If the model emitted `DialogueChapter` directly it could set `series`/`volume`/`schema_version`/`artifact_kind`/`status`/`review_required` and emit invented-but-canonical-looking attributions. `validate_dialogue_against_segments` only catches *non-canonical* names — it cannot catch an invented-but-canonical speaker, nor verify status/review_required/perspective integrity. The proposal→assemble split is correct. Failure-isolation is real but mitigated by validate-before-write + cheap `--force` re-run (prior file untouched). For v1 light-novel chapter sizes, **Option A stands**. **Architect verdict: APPROVE WITH MINOR CHANGES** (see §10.3).

### 10.2 Critic lane
Principle–option consistency: ✓. Fair alternatives: ✓ (add option C below). Testable acceptance criteria: ✓ (tighten assertions, §10.3 #5). Concrete verification (`ruff` + per-slice `pytest`): ✓. Risks coverage: ✓. **Critic verdict: APPROVE after folding in the §10.3 refinements.**

### 10.3 Refinements folded in (authoritative)
1. **First-person/POV resolution** — `names.py`/slice D2 must implement: a first-person speaker tag ("I"/"me"/equivalent) resolves through the *resolved chapter narrator* to that narrator's canonical name (per v1 `review._canonicalise_*` and the "POV character is the narrator" rule). Narration speaker label is `"Narrator"`.
2. **Prompt includes the character roster** — `prompts.py`/D3 must inject the registry's canonical names + aliases to anchor attribution and suppress invented names. Keep `speaker_raw` free-text (the model still needs to express pronoun / "previous speaker" cases) and canonicalize defensively in the runner.
3. **Deterministic row ordering** — the runner assembles `dialogues` and `rejected_candidates` sorted by segment order (not model output order) so the working review file diffs cleanly across re-runs.
4. **Alternative C recorded & rejected** — "model emits `DialogueChapter` directly": rejected because it removes the trust boundary (cannot validate invented-but-canonical names, status/review_required, or perspective integrity).
5. **Tighter acceptance assertions** — (a) invalid segment reference ⇒ `ContractValidationError` raised AND no dialogue file written; (b) skip-existing ⇒ existing file content preserved (assert bytes unchanged).
6. **Candidate-count observability** — `context.py`/runner logs candidate & segment counts and emits a soft `WARNING` above a threshold to signal "Option-B / chunking territory". Confirmed: `characters_config_path` lives in `common/paths.py` beside `dialogue_chapter_path`; loader `load_character_registry` lives in `dialogue/config.py`.

### 10.4 Finalized ADR (supersedes §9)
- **Decision:** Option A — one structured per-chapter Codex call returning an internal `DialogueProposal`; the runner canonicalizes names, computes review state, then assembles and validates the trusted `DialogueChapter` (stage-local + cross validators) before writing; skip-existing unless `--force`.
- **Drivers:** trust-boundary integrity; reviewer safety (the dialogue JSON is the working review file); consistency / low surface area; whole-chapter context for narrator resolution.
- **Alternatives considered:** B (per-candidate calls + separate perspective pass) — deferred as the scale-up path for oversized chapters; C (model emits `DialogueChapter` directly) — rejected, no trust boundary.
- **Why chosen:** simplest deterministic contract around a single replaceable model call; reuses the proven `run_codex_ocr` boundary shape and injectable-seam test pattern; honors the user's stated recommendation.
- **Consequences:** the stage is non-deterministic (no byte-reproducibility); idempotency comes from skip-existing + validate-before-write; a new hard dependency on `characters.json`; a malformed response fails a whole chapter (acceptable — re-run is cheap and the prior file is intact).
- **Follow-ups:** batch-all-chapters CLI; prompt-escalation list for refusals; chunking / Option B for oversized chapters; optional model-response caching.

### 10.5 ✅ RESOLVED — alias resolution lives on the registry (R1, user-approved 2026-05-30)
v2 `CharacterRegistry` (`series/contracts.py:32-40`) had only `has_character(name)` (exact name match), and the cross-validator accepts a speaker only if `has_character(speaker)` is true (`validators.py:317-321`) — so alias→canonical resolution (Principle 3, test cases 4 & 6) had no backing code. **Decision: R1.** Add additive `CharacterRegistry.resolve(name) -> str | None` (exact name + alias match, **no fuzzy**) to `series/contracts.py` as a new slice **D0b** before D2; `names.py` becomes a thin wrapper over it; Stage 4/5 reuse it. v1's `fuzzy_find` + raw-passthrough remain deliberately dropped (fuzzy = follow-up).

### 10.6 Additional refinements folded in (from the returned agents; authoritative)
7. **Omitted candidates → explicit `RejectedCandidate(reason="model_omitted")`** and stray ids → `reason="model_stray_segment"`, so §4.5 coverage is a hard gate, not a soft flag (resolves the §4.4/§4.5 double-rule). Folded into §4.4.
8. **D3 payload delivery resolved** — no `-i` image flag; payload JSON appended to the final positional `prompt` argv element; the "exact argv" test asserts no dangling `-i`. Folded into §4.1.
9. **`load_character_registry` is series-shared**, not `dialogue/config.py`-private (scenes/generation reuse). Folded into §4.6.
10. **Two added tests:** (a) unknown `--chapter` fails clearly BEFORE any model call (new `--chapter` membership logic is untested ground in transform); (b) `review_required` is computed from *canonicalized* speakers, not the raw proposal. Added to §6 as cases 10–11.
11. **CLI safety doc:** `--force` destroys a human-edited chapter file; the deferred batch-all CLI must NOT default to `--force` (a `--only-missing` mode is the safe batch pattern). Folded into §4.7 follow-ups.

### 10.7 Verdicts
- **Opus Architect:** REQUEST CHANGES → resolved by §10.5 decision + §10.6 items 7–9; core architecture (deterministic runner, injectable seam, proposal↔artifact split, Option A, validate-before-write, skip-existing) APPROVED unchanged.
- **Critic A:** APPROVE after folding §10.3/§10.6 refinements.
- **Critic B (CONDITIONAL APPROVE):** three slice-spec clarifications (D3 argv, loader placement, omitted-candidate rule) — all folded in (§10.6 items 7–9).

**Consensus status: APPROVED contingent on the §10.5 user decision. Plan = PENDING USER APPROVAL. No execution performed.**
