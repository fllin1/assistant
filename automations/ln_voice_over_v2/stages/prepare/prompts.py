"""OCR prompts for the LNVO v2 prepare stage."""

from __future__ import annotations

# Framing matters: gpt-5.5 on ChatGPT-account auth refuses prompts that name the
# source as a copyrighted publication and ask for full-page verbatim transcription.
# This prompt frames the call as mechanical image-to-text extraction (OCR), which
# the model is willing to perform. Verified live on both a cover page and a dense
# body page from a real volume.
OCR_PROMPT = (
    "Perform OCR on this image. Return strictly the following JSON object "
    "and nothing else:\n"
    "\n"
    '{"transcript": str, "is_illustration": bool}\n'
    "\n"
    "- transcript: every readable character in the image, as a single UTF-8 "
    "string. Preserve line breaks (\\n for soft, \\n\\n between paragraphs). "
    "For multi-column layouts, read each column top-to-bottom, then in "
    "left-to-right column order. If furigana appears next to kanji, include "
    "the furigana inline in parentheses immediately after the kanji.\n"
    "- is_illustration: true if and only if there is no readable text at all "
    "(the image is a full-bleed illustration or blank page); transcript must "
    'be "" in that case.\n'
    "- Do not paraphrase, summarize, redact, or translate. OCR is a "
    "mechanical task; output the characters that are present.\n"
    "- Output raw JSON. No markdown fences, no commentary.\n"
)
