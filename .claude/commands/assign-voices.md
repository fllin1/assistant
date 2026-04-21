---
argument-hint: <series-slug>[/<volume-slug>]
---

# Assign Voices — Propose a Voice Cast for a Series or Volume

Propose and apply per-character TTS voice assignments for a light-novel series, following the tiered strategy from `automations/ln_voice_over/docs/6-voice-assignment.md`.

**Usage:** `/assign-voices <series-slug>` or `/assign-voices <series-slug>/<volume-slug>`

Examples:
- `/assign-voices classroom-of-the-elite-year-2` — aggregates dialogue counts across all volumes that have reviewed chapters.
- `/assign-voices classroom-of-the-elite-year-2/v7` — restricts dialogue counts to volume v7.

Voice assignments are **series-level** — assigning a voice writes to `projects/<series>/config/voices.json`, which every volume in the series shares. This is by design: the whole point of the series layout is voice continuity across volumes.

## Instructions

### Step 1: Load the assignment plan

Run the prepare script with the argument from `$ARGUMENTS`:

```
uv run python -m automations.ln_voice_over.scripts.prepare_voice_assignment "$ARGUMENTS"
```

Capture the JSON output. It contains:
- `series`, `volumes_scanned`
- `tier_thresholds` — line-count cutoffs for tiers S/A/B/C/D and the voice-provider strategy for each tier
- `defaults` — the narrator / male / female fallback voices
- `characters` — each registered character with their dialogue count, tier, and current voice (if any)
- `available_voices` — catalogs for OpenAI, Kokoro (American + British), and Edge (en-US curated)
- `voices_in_use` — voices already mapped to some character (don't reassign these)

### Step 2: Decide what to propose

For each character whose `current_voice` is `null`, pick a voice according to the **tier strategy**:

| Tier | Lines    | Strategy                                                                                       |
|------|---------:|------------------------------------------------------------------------------------------------|
| S    | 500+     | OpenAI voice. Protagonist/narrator — needs a distinct, pleasant voice (heard constantly).      |
| A    | 100–499  | OpenAI voice. Major character — unique, well-matched.                                          |
| B    | 20–99    | Kokoro **American** voice matched to personality.                                              |
| C    | 5–19     | Kokoro (any) or Edge en-US. Unique voice is nice but not essential.                            |
| D    | <5       | Skip — gender default suffices.                                                                |

**Matching logic:**
1. Respect the character's gender (`gender` field). Don't propose a male voice for a female character or vice versa. Gender "unknown" → pick neutral or infer from description/role if possible.
2. Avoid any voice already in `voices_in_use` (that voice is taken by another character).
3. Match **personality** to voice description — e.g. authoritative character → `onyx`; cheerful/bright character → `nova`; calm/analytical → `echo`; warm/friendly → `coral` or `af_heart`. Use the character's `description` field as the primary signal.
4. For Tier B/C, read Kokoro voice names in the catalog: American female voices have prefix `af_`, American male `am_`, British female `bf_`, British male `bm_`.
5. Leave Tier D alone unless the user explicitly asked to include them.

If a character already has a `current_voice`, **do not propose a change** unless you see an obvious mismatch (e.g. wrong gender). Voice continuity is valuable.

### Step 3: Present the proposed cast

Before applying anything, show the user a table of proposed assignments. Group by tier, and include:
- Character name
- Tier (S/A/B/C)
- Gender
- Lines
- Proposed voice + provider
- One-line rationale tying the voice to the personality

Also flag separately:
- Characters kept as-is (already assigned)
- Characters left unassigned (Tier D)

End the message by asking: *"Apply these assignments? (yes / no / edit)"*

If the user says **edit**, take their corrections and show an updated table, then ask again.

If the user says **no**, stop without applying.

### Step 4: Apply approved assignments

For each approved (new or changed) assignment, run:

```
uv run lnvo assign-voice <series>/<volume> "<Character Name>" <voice_id> --provider <provider>
```

The `<series>/<volume>` form is fine — the CLI writes to the series config regardless. Use the `$ARGUMENTS` value verbatim when it already contains a slash; otherwise append `/v1` (or any volume) so the CLI accepts it.

After applying, run `uv run lnvo show-voices $ARGUMENTS` to confirm the final state.

### Step 5: Report

Summarize:
- Number of new assignments applied
- Number of changes to existing assignments (if any)
- Any characters that still have no voice (tier D, or gender=unknown that you couldn't place)
- A reminder that the user can audition any voice with `lnvo audition <voice-id> --character "<name>" --book <series>/<volume>` and call `/assign-voices` again to change a pick.

## Notes

- **Don't audition voices from the skill.** TTS audio can't reach the agent. The user has to audition themselves.
- **Each voice goes to at most one character.** The proposal must not assign the same voice to two people — check your picks against both the `voices_in_use` list and voices you're proposing in this run.
- **Don't touch the defaults.** `default_narrator`, `default_male`, `default_female` are edited by hand in `voices.json`, not via the CLI. Don't propose changes to them.
