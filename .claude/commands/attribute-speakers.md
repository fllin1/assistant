---
argument-hint: <book-slug> [<chapter-number>]
---

# Attribute Speakers — Map Dialogue Segments to Characters via Sonnet Agents

Attribute each dialogue segment in a chapter to a speaker by spawning parallel Sonnet agents. Sub-agents receive chunk JSON inline and return attributions inline — no tool calls on their side, so the skill runs unattended.

**Usage:**
- `/attribute-speakers <book-slug> <chapter-number>` — attribute a single chapter
- `/attribute-speakers <book-slug>` — attribute every chapter in the volume that doesn't already have an attribution file

Examples:
- `/attribute-speakers classroom-of-the-elite-year-2/v7 2`
- `/attribute-speakers classroom-of-the-elite-year-2/v4`

## Instructions

You are orchestrating speaker attribution for a light novel. Python scripts do the file I/O and LLM-free bookkeeping; sub-agents do the language work inline.

Parse `$ARGUMENTS`: the first token is the book slug (`<series>/<volume>`). If a second token is present, it's the chapter number and you run single-chapter mode. If it's missing, you run **volume mode**.

### Single-chapter mode

Run the four steps below once for the given chapter.

#### Step 0: Detect POV character

```
python -m automations.ln_voice_over.scripts.detect_pov <slug> <chapter_number>
```

This script does no LLM work — it just builds an opening snippet. Capture its JSON.

- `status == "already_set"`: report `"POV: <pov_character>"` and skip to Step 1.
- `status == "needs_detection"`:
  1. Use the **Read** tool to load `snippet_path`.
  2. Spawn ONE sub-agent with `model: "sonnet"` and the prompt below. Substitute `{snippet}` with the file contents you just read.

     ---

     You are identifying the first-person narrator of a light novel chapter opening.

     Snippet:
     ```
     {snippet}
     ```

     If the chapter is narrated in first person (the protagonist refers to themselves as "I" / "me"), return the narrator's name **exactly as written in the text** (e.g. `Ayanokouji`, `Horikita Suzune`, `Miyake`). If the chapter is third-person (everyone is referred to by name, no first-person "I" protagonist), return the literal string `null`.

     Reply with ONE LINE: the name or `null`. No explanation, no quotes, no JSON, no tool calls.

     ---
  3. Take the agent's one-line reply as `<pov_value>` and persist it:

     ```
     python -m automations.ln_voice_over.scripts.save_pov <manifest_path> <chapter_number> <pov_value>
     ```
  4. Report `"Detected POV: <name>"` or `"Detected POV: null (third-person)"`.

#### Step 1: Prepare chunks

```
python -m automations.ln_voice_over.scripts.prepare_chunks <slug> <chapter_number>
```

Capture the JSON output (contains `pov_character`, `dialogue_count`, `chunks[]`, `tmp_dir`, etc.). Report chapter title, POV, total segments, and dialogue count.

#### Step 2: Attribute chunks

For each chunk in `chunks[]`:

1. Use the **Read** tool to load `chunk_path` — the file is a JSON array of segments.

Then spawn **up to 8 sub-agents in parallel** using `model: "sonnet"`. Each agent gets this prompt (substitute `{pov_character}` and `{chunk_json}`):

---

You are attributing dialogue speakers in a light novel chapter. The narrator ("I") is {pov_character}.

Your chunk (JSON array of segments, narration + dialogue interleaved):

```json
{chunk_json}
```

For each DIALOGUE segment, determine who is speaking by:
1. Checking narration AFTER the dialogue for speech tags ("said Horikita", "she replied", "I asked").
2. Checking narration BEFORE — but a tag before may describe the PREVIOUS dialogue.
3. "I said/replied/asked" = {pov_character}.
4. Resolving pronouns ("he/she said") from context.
5. Inferring from conversation flow when no tag exists.
6. If the marked text is a quoted word or phrase embedded in narration (not actual speech), use "Narrator".
7. If the speaker is unnamed/unidentified (staff, announcer, bystander), use "Unknown".

Reply with **only** a JSON object mapping dialogue segment index (string) to speaker name, wrapped in a single fenced `json` block. Use character names as they appear in the text (e.g. "Horikita", "Chabashira-sensei", "Mii-chan"). Include EVERY dialogue segment.

Example:

```json
{"3": "Chabashira-sensei", "6": "Horikita", "8": "Narrator", "11": "I"}
```

Where "I" means the narrator ({pov_character}). No explanation, no prose, no tool calls — just the fenced JSON block.

---

If the chapter has more than 8 chunks, run remaining chunks in a second batch after the first completes.

If `pov_character` is `null` (third-person chapter), the `"I = {pov_character}"` line reads as `"I = None"` — harmless because a third-person chapter shouldn't produce any `"I"` speakers. Pass it through as-is.

#### Step 3: Merge and save

Parse the JSON object out of each sub-agent's final reply (strip the markdown fence). Build a map keyed by chunk index (string):

```json
{"0": {"3": "Horikita", ...}, "1": {"60": "I", ...}, ...}
```

Pass it to the merge script via `--results`:

```
python -m automations.ln_voice_over.scripts.merge_attributions '<metadata_json>' --results '<results_json>'
```

The script merges overlaps, normalizes "I" → POV character (skipped when POV is null), writes `extracted/chapter_<file_id>/claude-sonnet_skill_<date>.json`, cleans up `tmp_dir`, and prints a report.

Report the save path and speaker breakdown.

### Volume mode

When no chapter number is supplied:

1. Read the manifest:

   ```
   python -c "import json, pathlib; print(pathlib.Path.home() / '.assistant' / 'ln_voice_over' / 'projects' / '<slug>' / 'chapters' / 'manifest.json')"
   ```

   Then use the **Read** tool on that path. The manifest is a list of `{number, title, file, pov_character}` entries.

2. For each entry, compute the attribution output directory: `~/.assistant/ln_voice_over/projects/<slug>/extracted/chapter_<file_id>/` where `<file_id>` is the `file` field with the `chapter_` prefix and `.txt` suffix stripped (e.g. `chapter_05.txt` → `05`). Use **Glob** to check whether any `claude-sonnet_skill_*.json` already exists in that directory. If yes, skip the chapter.

3. For each chapter that needs attribution, run **Steps 0–3 from single-chapter mode** using that chapter's `number`. Process chapters sequentially — parallelism stays at the chunk level.

4. After the loop, print a volume summary: one line per chapter stating `processed | skipped (already attributed) | failed`, plus a total.

Be concise in your user-facing updates — one short status message per chapter is enough.
