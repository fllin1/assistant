# Attribute Chapter — Speaker Attribution via Sonnet Agents

Attribute all dialogue segments in a chapter by spawning parallel Sonnet agents.

**Usage:** `/attribute-chapter <book-slug> <chapter-number>`

Example: `/attribute-chapter classroom-of-the-elite-year-2 2`

## Instructions

You are orchestrating speaker attribution for a light novel chapter. Your job is to split the work across multiple Sonnet agents, merge their results, and save the output.

### Step 1: Load the chapter

Read the parsed chapter JSON from:
`~/.assistant/ln_voice_over/projects/$ARGUMENTS/parsed/chapter_<NN>.json`

Parse the arguments: first word is the book slug, second is the chapter number (zero-pad to 2 digits).

Also read the manifest at `~/.assistant/ln_voice_over/projects/<slug>/chapters/manifest.json` to get the `pov_character` for this chapter.

Count the total dialogue segments and report to the user.

### Step 2: Split into chunks and spawn agents

Split the chapter segments into chunks of ~150 segments each (with ~20 segment overlap between consecutive chunks for context continuity). Write each chunk to a temporary JSON file under the project directory.

Spawn **up to 6 Sonnet agents in parallel** (one per chunk) using `model: "sonnet"`. Each agent gets this prompt:

---

You are attributing dialogue speakers in a light novel chapter. The narrator ("I") is {pov_character}.

Read the file at {chunk_path}. It contains a JSON array of segments (narration + dialogue interleaved).

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

Write the result to {output_path}.

---

### Step 3: Merge results

After all agents complete:
1. Read each agent's output JSON
2. Merge into a single dict (for overlapping segments, keep the attribution from the chunk where the segment is NOT at the edge — prefer the chunk where it has more surrounding context)
3. Normalize "I" → the pov_character name
4. Report: total dialogues, how many attributed, how many Unknown, how many Narrator

### Step 4: Save

Generate a filename with today's date: `claude-sonnet_skill_YYYYMMDD.json`

Save the merged result as JSON to:
`~/.assistant/ln_voice_over/projects/<slug>/extracted/chapter_<NN>/claude-sonnet_skill_YYYYMMDD.json`

Create the directory if it doesn't exist.

Format: `{"index": "speaker_name"}` — flat dict, same format as other extraction sources.

Report the save path and a brief summary to the user.
