---
argument-hint: <book-slug> [<chapter>] [<judge-model>]
---

# Review Attribution — Judge Pass on Speaker Attributions

Run a second LLM pass over an attributed chapter with **different chunk boundaries** (shifted-overlap) to surface real attribution disagreements, then resolve each disagreement with **Opus** + near-context. The result is the canonical `reviewed/chapter_<id>.json`.

**Usage:**
- `/review-attribution <book-slug> <chapter> [<judge-model>]` — review one chapter
- `/review-attribution <book-slug>` — review every attributed chapter in the volume

Examples:
- `/review-attribution classroom-of-the-elite-year-2/v4 5`
- `/review-attribution classroom-of-the-elite-year-2/v4 07_1 opus`
- `/review-attribution classroom-of-the-elite-year-2/v4`

`judge-model` defaults to `sonnet`. **Flag resolution always uses Opus** regardless of what the judge pass ran on — two different models in the loop is the point.

## Instructions

You are orchestrating a judge pass. Python scripts do file I/O; sub-agents do language work inline and reply with JSON in fenced blocks — no tool calls on their side.

Parse `$ARGUMENTS`: first token is the book slug. Remaining tokens: `chapter` (optional) and `judge-model` (optional). If a trailing token matches `sonnet` or `opus`, treat it as the judge-model; otherwise treat the second token as the chapter id.

### Single-chapter mode

Run the seven steps below once for the given chapter.

#### Step 0: Skip check

If `~/.assistant/ln_voice_over/projects/<slug>/reviewed/chapter_<id>.json` already exists, use `AskUserQuestion` with a single question `"Chapter <id> is already reviewed. Re-review?"`, options `["Skip", "Re-review"]`, default Skip. If the user picks Skip, report that and exit single-chapter mode.

#### Step 1: Prepare judge chunks

```
python -m automations.ln_voice_over.scripts.prepare_judge_chunks <slug> <chapter>
```

Capture the JSON (`chapter_id`, `pov_character`, `chunks[]`, `judge_dir`, etc.). Report chapter id, POV, total segments.

#### Step 2: Run the judge pass

For each chunk in `chunks[]`:

1. Use the **Read** tool to load `chunk_path`.
2. Spawn up to **8 parallel** sub-agents using `model: "<judge-model>"`. Each gets the prompt below (substitute `{pov_character}` and `{chunk_json}`):

---

You are auditing dialogue speaker attributions in a light novel chapter. The narrator ("I") is {pov_character}.

Your chunk (JSON array of segments, narration + dialogue interleaved):

```json
{chunk_json}
```

For each DIALOGUE segment, determine who is speaking using:
1. Speech tags in the narration AFTER the dialogue ("said Horikita", "she replied", "I asked").
2. Speech tags BEFORE — careful, a tag before may describe the PREVIOUS dialogue.
3. "I said/replied/asked" = {pov_character} speaking actual quoted dialogue → use the POV character's name.
4. Pronouns → resolve from scene context.
5. Conversation alternation in multi-party scenes.
6. If the quoted text is embedded in narration (not actual speech) — e.g. `"experiments"` — use "Narrator".
7. **Mis-tagged narration**: if a "dialogue" segment is a long block of first-person narration, exposition, or inner thought (typically >300 characters, no speech tag at either end, no clear utterance boundary, often spans multiple sentences), the parser has mis-tagged narration as dialogue. Use **"Narrator"**, NOT the POV character's name.
8. If the speaker is unnamed / staff / bystander, use "Unknown".

Reply with **only** a JSON object mapping dialogue segment index (string) to speaker name, wrapped in a single fenced `json` block. Include EVERY dialogue segment. Use names as they appear in the text ("Horikita", "Chabashira-sensei") — the pipeline canonicalises downstream.

Example (POV = Ayanokouji):
```json
{"40": "Horikita", "43": "Narrator", "47": "Ayanokouji", "51": "Narrator"}
```

Index 43 is an embedded quote. Index 51 is a long mis-tagged narration block. Index 47 is Ayanokouji's actual dialogue.

No explanation, no prose, no tool calls.

---

Collect each sub-agent's reply into `{chunk_idx_str: attrs_dict}`.

#### Step 3: Merge judge attributions

```
python -m automations.ln_voice_over.scripts.merge_judge_attributions '<metadata_json>' --results '<results_json>'
```

Prints the save path and total attributed.

#### Step 4: Diff judge vs original

```
python -m automations.ln_voice_over.scripts.diff_attributions <slug> <chapter_id>
```

Capture the JSON — it has `flag_count` and `flags[]`. If `flag_count == 0`, skip to Step 6 with corrections = `[]`.

Report `"N disagreements to resolve"`.

#### Step 5: Resolve each flag with Opus

For each flag in `flags[]`, spawn ONE sub-agent with `model: "opus"` using this prompt (substitute the flag fields):

---

You are resolving a single dialogue attribution disagreement in a light novel. Two attempts disagreed on who is speaking — decide which is correct (or give a third answer if both are wrong).

**Dialogue (index {index}):** `{segment_text}`

**Context before:**
{context_before joined with newlines}

**Context after:**
{context_after joined with newlines}

**Candidate A (original Sonnet pass):** `{original_speaker}`
**Candidate B (judge pass):** `{judge_speaker}`

Use speech tags ("said X", "she replied"), conversation alternation, and who is physically present in the scene.

**Convention reminder**: a long first-person inner-monologue or exposition block (>300 chars, no speech tag) that the parser tagged as "dialogue" is mis-tagged narration — speaker is **"Narrator"**, NOT the POV character's name. The POV character's name only belongs on actual quoted dialogue they speak.

Reply with a JSON object:

```json
{"speaker": "<canonical name, or Narrator / Unknown>", "reason": "<one short sentence>"}
```

No prose outside the fenced block, no tool calls.

---

Parse each JSON reply. Collect `{index, speaker, reason, original_speaker, judge_speaker, segment_text}`.

Build the corrections list as `[{index, speaker}, …]` directly from the Opus verdicts, filtering out entries where `speaker == original_speaker` (those are no-ops after canonicalisation and only add noise to the report sidecar).

#### Step 6: Apply corrections

```
python -m automations.ln_voice_over.scripts.apply_corrections '<slug>' '<chapter_id>' '<corrections_json>'
```

The script merges the parsed chapter + original attributions + corrections into `reviewed/chapter_<id>.json`, sets `reviewed=True`, and writes a `chapter_<id>_report.json` sidecar.

#### Step 7: Report

Report to the user:
- save path
- flag count (disagreements found)
- corrections applied (with before → after for each)
- accepted-as-is count (Opus verdict matched the original — no correction needed)

### Volume mode

When no chapter argument is supplied:

1. Use **Read** to load `~/.assistant/ln_voice_over/projects/<slug>/chapters/manifest.json`. It's a list of `{number, title, file, pov_character, subchapter?}` entries.

2. For each entry, derive the chapter id from the `file` field (`chapter_07.txt` → `07`, `chapter_07_1.txt` → `07_1`). Skip entries with no `extracted/chapter_<id>/claude-sonnet_skill_*.json` (nothing to review — run `/attribute-speakers` first).

3. Run **Steps 0–7** for every remaining entry in order. The Step 0 `AskUserQuestion` is the skip gate for already-reviewed chapters (default Skip).

4. After the loop, print a volume summary: one line per chapter stating `reviewed | skipped | no attribution`, plus totals.

Keep user-facing updates terse: one short line per chapter.
