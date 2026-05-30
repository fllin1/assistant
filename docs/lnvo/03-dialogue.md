Dialogue detects spoken dialogue, assigns speakers, and resolves chapter perspective.

## Purpose

| Output | Contract |
| --- | --- |
| Dialogue chapter | `<volume>/dialogue/chapter_XX[_M].json` stores dialogue rows, rejected candidates, perspective, and review state. |

Sufficient handoff: Scenes can treat accepted dialogue rows as spoken beats and remaining segments as narration candidates.

## Inputs

```text
<volume>/volume_index.json
<volume>/segments/chapter_XX[_M].json
<series>/config/characters.json
<series>/config/story_profile.json
```

## Dialogue Chapter

```json
{
  "schema_version": 1,
  "artifact_kind": "dialogue_chapter",
  "series": "classroom-of-the-elite-year-2",
  "volume": "v4",
  "chapter_id": "chapter_07_1",
  "status": "accepted",
  "review_required": false,
  "perspective": {
    "status": "detected",
    "narrator": "Ayanokouji Kiyotaka"
  },
  "dialogues": [
    {
      "segment_id": "seg_000012",
      "speaker": "Horikita Suzune"
    }
  ],
  "rejected_candidates": [
    {
      "segment_id": "seg_000018",
      "reason": "Quoted narration, not spoken dialogue."
    }
  ],
  "review_notes": []
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `artifact_kind` | yes | `dialogue_chapter`. |
| `status` | yes | `accepted` or `needs_review`. |
| `review_required` | yes | review gate flag. |
| `perspective.status` | yes | `unset` or `detected`. |
| `perspective.narrator` | yes | canonical character name or `null`. |
| `dialogues` | yes | accepted or proposed spoken dialogue rows. |
| `dialogues[].segment_id` | yes | referenced segment id. |
| `dialogues[].speaker` | yes | canonical character name or `Unknown`. |
| `rejected_candidates` | yes | quote-like segments rejected as dialogue. |
| `review_notes` | yes | concise review notes. |

Review edits update this file directly until `status: accepted`.

## Validation

- every referenced `segment_id` resolves;
- each segment appears at most once in `dialogues`;
- every speaker is canonical or `Unknown`;
- detected `perspective.narrator` is canonical or `null`;
- downstream stages require `status: accepted`.

Two validators run before any write (mirroring transform): a stage-local
`validate_dialogue_artifact` and the cross-artifact
`validate_dialogue_against_segments`.

| Validator | Checks |
| --- | --- |
| stage-local (`stages/dialogue/validation.py`) | every `quote_candidate` segment is classified into `dialogues` xor `rejected_candidates` (`uncovered_candidate`); no id in both (`candidate_in_both`); `status == needs_review` iff `review_required` (`status_mismatch`). |
| cross-artifact (`pipeline/validators.py`) | `segment_id` resolution, no duplicate dialogue segment, speaker canonical-or-`Unknown`, detected narrator canonical-or-`null`. |

## CLI

```text
# whole volume (default): attribute every chapter in volume_index.json
python -m automations.ln_voice_over_v2.stages.dialogue \
  --series <series> --volume <volume> [--workers N] [--timeout SECONDS] [--data-root DIR] [--force]

# one chapter
python -m automations.ln_voice_over_v2.stages.dialogue \
  --series <series> --volume <volume> --chapter <chapter_id> [--timeout SECONDS] [--data-root DIR] [--force]
```

`--chapter` is optional. Omit it to run the whole volume, dispatching `--workers`
chapters concurrently (default 4); each chapter is a separate `codex` call.
`--timeout` bounds that single per-chapter `codex` call in seconds (default
600); raise it for unusually long chapters that otherwise time out, or lower it
to fail fast.
Chapter ids come from `volume_index.json` (`chapter_01`, `chapter_07_1`,
`chapter_00` for front matter); you do not need to know them for a whole-volume
run, and an unknown `--chapter` error lists the available ids.

Single-chapter mode prints the written dialogue path (exit 0). Whole-volume mode
prints one line per chapter (path, `skipped (exists)`, or `error: …`) and a
`written / skipped / failed` summary, exiting 1 if any chapter failed. In both
modes a `ContractValidationError` prints each problem and exits 2. Existing
dialogue files are skipped unless `--force`, so a whole-volume re-run only fills
in missing chapters and never clobbers reviewed ones.

## Implementation Notes

Unlike transform, dialogue is **not** byte-deterministic: it makes one LLM call
per chapter. Idempotency comes from skip-existing plus validate-before-write,
not reproducibility.

### Model boundary

The model proposes; the runner decides. `stages/dialogue/agent.py::run_codex_dialogue`
mirrors the prepare-stage `run_codex_ocr` boundary (a `codex exec` subprocess with
`--ignore-user-config --ephemeral --skip-git-repo-check -s read-only`, strict JSON
parse, `RuntimeError` on non-zero exit, `ContractValidationError` on malformed
output) but is text-only (no `-i` image flag). The chapter payload and character
roster are built by `prompts.build_prompt` and appended to the prompt. The model
returns only an internal `DialogueProposal` (per-candidate `is_dialogue` /
`speaker_raw` / `reason`, plus `narrator_raw` and `review_notes`); it never emits
the persisted `DialogueChapter`. The runner accepts an injectable `attribute_fn`
seam so tests never spawn `codex`.

### Assembly and review state

The runner restricts decisions to the chapter's `quote_candidate` segments and
assembles rows in segment order:

- a candidate the model omitted becomes `RejectedCandidate(reason="model_omitted")`;
- a non-candidate id the model returned becomes `RejectedCandidate(reason="model_stray_segment")` when it resolves to a real segment, otherwise it is dropped with a review note;
- accepted candidates become `DialogueRow`s with a canonicalized speaker.

`review_required` is computed from the **canonicalized** speakers and is `true`
when any accepted speaker is `Unknown`, the narrator is unresolved, a candidate
was omitted, or any review note exists. `status` is `needs_review` iff
`review_required`, else `accepted`.

### Name normalization

Speaker and narrator labels resolve through `CharacterRegistry.resolve` (exact
canonical name or alias match, **no fuzzy matching**). A first-person speaker tag
(`I`/`me`/...) resolves through the chapter narrator. Unresolved speakers become
`Unknown`; unresolved narrators become `null`. No invented characters.

### Inputs and config

`config/characters.json` is **required and has no packaged fallback** (character
lists are series content); a missing file raises before any model call.
`config/story_profile.json` is optional context (its `rules.default_narrator`
seeds a narrator hint) and resolves via the shared transform resolver.

### Reviewer safety

The dialogue JSON is the working review file. A re-run **skips** an existing file
unless `--force`; validate-before-write means a bad run never corrupts an existing
good file.

## Debugging & Known Issues

Branch: `feat/lnvo-v2-dialogue-stage3` (implemented 2026-05-30; not merged/pushed).
Model boundary: `gpt-5.5` via `codex exec` (text-only, strict JSON).

### Where to look
- **The artifact is the review file.** Open `<volume>/dialogue/<chapter>.json`:
  `status` (`accepted`/`needs_review`), `review_required`, `perspective`,
  `dialogues[]`, `rejected_candidates[]` (with `reason`), `review_notes[]`.
- **Reject reasons** are diagnostic: `model_omitted` (model returned no decision
  for a candidate), `model_stray_segment` (model classified a non-candidate),
  or the model's own free-text reason for a genuine reject.
- **`Unknown` speaker or `null` narrator** means `CharacterRegistry.resolve`
  found no exact name/alias — fix `config/characters.json`, not the code.
- **Model call:** `stages/dialogue/agent.py::run_codex_dialogue`; prompt in
  `prompts.py`. A refusal / malformed JSON raises `ContractValidationError`
  (`dialogue_malformed`); a non-zero `codex` exit or a per-chapter timeout
  (default 600s, override with `--timeout`) raises `RuntimeError`. To inspect a
  single chapter, run with `--chapter <id>` and read stderr.
- Stage 3 is **not** byte-deterministic; idempotency is skip-existing + `--force`.

### Known open issues (from code review — NOT yet fixed)
1. **Silent duplicate-decision drop.** Two model decisions for the same candidate
   collapse last-wins with no review flag (`runner.py`, `decision_by_id`).
   Contradictory output is accepted clean instead of flagged.
2. **`narrator_hint` is dead context.** `build_chapter_payload` puts
   `story_profile.rules.default_narrator` into the payload, but `DIALOGUE_PROMPT`
   never tells the model to use it — weakens narrator detection.
3. **First-person precedence.** `names.canonical_speaker` resolves `I`/`me`
   through the narrator *before* the registry lookup, so a character literally
   named `I`/`me` would be shadowed (low likelihood, but reversed precedence).

### Orchestration gotchas (when fixing via the `codex` CLI)
- Use `codex exec --sandbox workspace-write` for writes; `resume` defaults to
  read-only (override with `-c sandbox_mode=workspace-write`).
- The PostToolUse `ruff --fix` hook strips a just-added import if its first use
  lands in a *later* edit — add the import and its usage in the same change.
- `codex exec` sometimes ends a turn after narrating intent without applying
  patches; re-run or resume, and verify with `ruff` + `pytest` yourself.

## Design History

- **2026-05-30 — Stage 3 designed via ralplan consensus and implemented by Codex agents** (`.omc/plans/lnvo-v2-dialogue-stage3.md`). Architect raised a blocker: v2 `CharacterRegistry` had only `has_character` (exact, no aliases), so alias normalization had no backing code. Resolved by user decision **R1** — added an additive `CharacterRegistry.resolve(name) -> str | None` (exact name + alias, no fuzzy). Other consensus refinements folded in: model proposes an internal `DialogueProposal` (runner assembles the trusted artifact); per-chapter single call (Option A; per-candidate Option B deferred); omitted/stray candidates become explicit `RejectedCandidate`s; rows sorted by segment order; skip-existing unless `--force`; series-shared `load_character_registry`.
