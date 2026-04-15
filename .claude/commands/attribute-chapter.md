# Attribute Chapter — Speaker Attribution via Sonnet Agents

Attribute all dialogue segments in a chapter by spawning parallel Sonnet agents.

**Usage:** `/attribute-chapter <book-slug> <chapter-number>`

Example: `/attribute-chapter classroom-of-the-elite-year-2 2`

## Instructions

You are orchestrating speaker attribution for a light novel chapter. Python scripts handle all file I/O; you just run them and spawn agents.

### Step 1: Prepare chunks

Run the prepare script — it reads the chapter, splits into overlapping chunks, and prints metadata as a single JSON line:

```
python automations/ln_voice_over/scripts/prepare_chunks.py <slug> <chapter_number>
```

Parse the arguments from `$ARGUMENTS`: first word is the book slug, rest is the chapter number.

Capture the JSON output — it contains `pov_character`, `dialogue_count`, `chunks` (each with `chunk_path` and `output_path`), and other metadata you'll need.

Report to the user: chapter title, POV character, total segments, dialogue count.

### Step 2: Spawn agents

Spawn **up to 8 Sonnet agents in parallel** (one per chunk) using `model: "sonnet"`. Each agent gets this prompt:

---

You are attributing dialogue speakers in a light novel chapter. The narrator ("I") is {pov_character}.

Run this command to read the chunk:
```
cat {chunk_path}
```

It contains a JSON array of segments (narration + dialogue interleaved).

For each DIALOGUE segment, determine who is speaking by:
1. Checking narration AFTER the dialogue for speech tags ("said Horikita", "she replied", "I asked")
2. Checking narration BEFORE — but a tag before may describe the PREVIOUS dialogue
3. "I said/replied/asked" = {pov_character}
4. Resolving pronouns ("he/she said") from context
5. Inferring from conversation flow when no tag exists
6. If the marked text is a quoted word or phrase embedded in narration (not actual speech), use "Narrator"
7. If the speaker is unnamed/unidentified (staff, announcer, bystander), use "Unknown"

Return ONLY a JSON object mapping dialogue segment index to speaker name. Use character names as they appear in the text (e.g., "Horikita", "Chabashira-sensei", "Mii-chan"). Example format:

```json
{"3": "Chabashira-sensei", "6": "Horikita", "8": "Narrator", "11": "I"}
```

Where "I" means the narrator ({pov_character}). Include EVERY dialogue segment. Be concise — no explanation needed, just the JSON.

Write the result by running:
```
cat > {output_path} << 'ATTRIBUTION_EOF'
<your JSON here>
ATTRIBUTION_EOF
```

---

### Step 3: Merge and save

After all agents complete, run the merge script. Pass the metadata JSON (from step 1) as a single-quoted argument:

```
python automations/ln_voice_over/scripts/merge_attributions.py '<metadata_json>'
```

The script merges overlaps, normalizes "I" → POV character, saves the result, and cleans up temp files. It prints a JSON report.

Report the save path and speaker breakdown to the user.
