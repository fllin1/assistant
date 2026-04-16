# Review Chapter — Resolve Speaker Attribution Divergences

Review flagged speaker divergences in an attributed chapter and correct them.

**Usage:** `/review-chapter <book-slug> <chapter-number>`

Example: `/review-chapter classroom-of-the-elite-year-2 4b`

## Instructions

You are reviewing speaker attributions where two LLM sources (Gemini Flash and Claude Sonnet) disagreed. A Python script loads the chapter, flags, and surrounding context. Your job is to read the context and make a judgment call on each divergence.

### Step 1: Load review data

Run the prepare script:

```
python -m automations.ln_voice_over.scripts.prepare_review <slug> <chapter_number>
```

Parse the arguments from `$ARGUMENTS`: first word is the book slug, rest is the chapter number (zero-pad if needed, e.g. "4b" → "04b", "2" → "02").

Capture the JSON output. It contains the chapter metadata, POV character, and a list of divergences — each with surrounding context segments.

If `divergence_count` is 0, skip to Step 3 with an empty corrections array.

### Step 2: Analyze each divergence

For each divergence, examine the context and determine the correct speaker.

**Signals in priority order:**

1. **Speech tag after the dialogue** — "said Horikita", "she replied", "I asked". This is the strongest signal. Check the narration segment(s) immediately after the dialogue.
2. **Speech tag before the dialogue** — "Horikita spoke up:". Careful: a tag before may describe the PREVIOUS dialogue if there's no narration gap.
3. **First-person = POV character** — "I said/replied/asked" in narration means the POV character is speaking. But "I agreed" or "I figured" is a thought, not a speech tag.
4. **Pronouns** — "he said" / "she said" — resolve from context (who is male/female in the scene?).
5. **Conversation alternation** — In a two-person exchange, speakers alternate. Check surrounding attributed speakers.
6. **Content clues** — What is being said and who would logically say it.

**If the default context window (8 segments) is insufficient**, re-run the prepare script with a wider window:

```
python -m automations.ln_voice_over.scripts.prepare_review <slug> <chapter_number> --context 15
```

Then re-examine the uncertain divergence(s) with the additional context.

**For each divergence, decide:**
- Which source is correct (or if neither is — provide the right answer)
- Whether the current attribution (majority vote) needs changing

Build a JSON array of corrections — **only include entries where the current speaker is WRONG**:

```json
[
  {"index": 100, "new_speaker": "Horikita Suzune", "reason": "Narration at [101] says 'said Horikita'"},
  {"index": 894, "new_speaker": "Nagumo Miyabi", "reason": "He is addressing the group, conversation flow confirms"}
]
```

If all current attributions are already correct, use an empty array `[]`.

### Step 3: Apply corrections and save

Run the apply script, passing the corrections JSON:

```
python -m automations.ln_voice_over.scripts.apply_review '<slug>' '<chapter_id>' '<corrections_json>'
```

The script applies corrections, marks the chapter as reviewed, and saves to `reviewed/chapter_NN.json`.

Report to the user:
- How many divergences were reviewed
- How many corrections were made (with before → after details)
- How many were confirmed as-is
- The save path
