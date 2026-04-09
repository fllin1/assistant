"""Stage 3: PARSE — Split cleaned text into typed segments.

Reads cleaned chapter text and classifies each block into segment types:
narration, dialogue, inner thought, scene break, or chapter header.

Key rule: no mid-sentence splitting. A narration paragraph containing
inline dialogue (e.g. She said "hello" and left.) stays as one narration
segment. This avoids choppy TTS output.

Segments are split at paragraph boundaries (double newline). Long narration
blocks (>MAX_SEGMENT_CHARS) are split at sentence boundaries.
"""

from __future__ import annotations

from pathlib import Path

from .models import Chapter, Segment, SegmentType


def classify_paragraph(paragraph: str) -> SegmentType:
    """Determine the segment type of a text paragraph.

    Classification rules (in priority order):
    1. Scene break patterns → SCENE_BREAK
    2. Chapter header patterns → CHAPTER_HEADER
    3. Full paragraph in quotes ("...") → DIALOGUE
    4. Italic/thought markers (*...*, _..._, em-dash) → INNER_THOUGHT
    5. Everything else → NARRATION

    A paragraph with mixed content (narration + inline quotes) is
    classified as NARRATION — the voice for the whole segment comes
    from the attribution stage.

    Args:
        paragraph: A single paragraph of text (no double-newlines inside).

    Returns:
        The SegmentType classification.
    """
    ...


def split_long_narration(text: str, max_chars: int = 500) -> list[str]:
    """Split a long narration block at sentence boundaries.

    Finds sentence-ending punctuation (. ! ? followed by space or end)
    and splits so each chunk is under max_chars. If a single sentence
    exceeds max_chars, it is kept whole.

    Args:
        text: The narration text to split.
        max_chars: Maximum characters per chunk.

    Returns:
        List of text chunks, each under max_chars when possible.
    """
    ...


def parse_chapter(
    cleaned_path: Path, chapter_number: int, title: str, pov_character: str | None = None
) -> Chapter:
    """Parse a cleaned chapter file into a Chapter with typed segments.

    Reads the file, splits into paragraphs, classifies each, and builds
    Segment instances. The first non-blank line is treated as a potential
    chapter header.

    Args:
        cleaned_path: Path to the cleaned chapter .txt file.
        chapter_number: Chapter number from the manifest.
        title: Chapter title from the manifest.
        pov_character: POV character name (from manifest), or None.

    Returns:
        A Chapter instance with its segments tuple populated.
        Speaker and confidence fields on segments are None at this stage.
    """
    ...
