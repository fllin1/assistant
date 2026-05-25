"""OCR prompts for the LNVO v2 prepare stage."""

from __future__ import annotations

OCR_PROMPT = """OCR this light-novel page and emit only this JSON object shape:
{"transcript": str, "is_illustration": bool}

Rules:
- Emit raw JSON only.
- Do not include prose, a preamble, or a postamble.
- Do not wrap the JSON in markdown code fences.
- Do not include trailing explanation or extra output.
- For two-column pages, read each column top-to-bottom, then read columns left-to-right.
- Preserve paragraph breaks in the transcript.
- Do not translate the text.
- Preserve furigana inline when present.
- If the page is a full-bleed illustration with no readable text, set transcript to ""
  and is_illustration to true.
"""
