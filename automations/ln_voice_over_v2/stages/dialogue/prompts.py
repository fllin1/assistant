"""Prompt construction for LNVO dialogue attribution."""

from .context import ChapterPayload

DIALOGUE_PROMPT: str = """You are the dialogue attribution stage for light novel voice-over.

Read the chapter payload and return STRICT JSON ONLY. Do not include markdown,
comments, code fences, prose, or any text outside the JSON object.

Return exactly this DialogueProposal shape:
{"decisions":[{"segment_id":str,"is_dialogue":bool,"speaker_raw":str|null,"speaker_gender":"male"|"female"|"unknown","reason":str}],"narrator_raw":str|null,"review_notes":[str]}

Rules:
- Only classify segments whose role is "candidate". Segments with role
  "narration" or "context" are background for turn-taking and continuity only;
  never emit a decision for them.
- Set is_dialogue=true only for true spoken dialogue.
- Set is_dialogue=false for quoted narration, titles, labels, thoughts that are
  not spoken aloud, sound effects, or other non-dialogue; include a short reason.
- For true dialogue, set speaker_raw to a provided roster name or alias when the
  speaker is roster-resolvable.
- If the speaker is named or labelled in the chapter but is absent from the
  roster, set speaker_raw to the exact in-text name or stable role label and set
  speaker_gender to "male", "female", or "unknown".
- If no speaker name or stable label is supported by the text, set
  speaker_raw=null and speaker_gender="unknown".
- Infer speaker_gender only from textual evidence such as pronouns, honorifics,
  titles, roles, first names, or surrounding context; use "unknown" if unclear.
- narrator_raw must be one of the provided roster names or aliases, otherwise null.
- If the payload includes a narrator_hint, treat it as the default narrator
  unless explicit in-chapter evidence overrides it; still return narrator_raw as
  a roster name/alias or null.
- Never invent names, aliases, speakers, narrators, gender evidence, or segment IDs.
- Use mechanical structured-attribution framing: base decisions on explicit
  attribution, turn-taking, local context, and provided roster evidence.
"""


def build_prompt(payload: ChapterPayload, roster: tuple[str, ...]) -> str:
    """Build the model prompt for dialogue attribution."""
    roster_lines = "\n".join(f"- {name}" for name in roster)
    roster_display = roster_lines if roster_lines else "- <empty>"
    roster_block = f"\n\nRoster names and aliases:\n{roster_display}\n\nChapter payload JSON:\n"
    return DIALOGUE_PROMPT + roster_block + payload.model_dump_json()
