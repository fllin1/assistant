"""Stage 3: PARSE — Split cleaned text into typed segments.

Reads cleaned chapter text and splits it into narration and dialogue segments.
The chapter header (first line) is extracted, then the remaining text is
stitched into a continuous block (double newlines in cleaned files are page
break artifacts, not real paragraph boundaries). Inline dialogue is extracted
at quote boundaries, and long narration chunks are split at sentence boundaries
for TTS quality.
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import CHAPTER_PATTERNS, MAX_SEGMENT_CHARS
from .models import Chapter, Segment, SegmentType


def _is_chapter_header(text: str) -> bool:
    stripped = text.strip()
    return any(p.search(stripped) for p in CHAPTER_PATTERNS)


# Captures quoted strings (straight or curly quotes) as separate groups
_QUOTE_PATTERN = re.compile(r'(["\u201c][^"\u201d]*["\u201d])')


def _extract_segments(text: str) -> list[tuple[SegmentType, str]]:
    """Split text into alternating narration/dialogue sub-segments."""
    parts = _QUOTE_PATTERN.split(text)
    result = []
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        if stripped[0] in '"\u201c' and stripped[-1] in '"\u201d':
            result.append((SegmentType.DIALOGUE, stripped))
        else:
            result.append((SegmentType.NARRATION, stripped))
    return result


def _find_sentence_boundaries(text: str) -> list[int]:
    """Return character indices where the text can be split between sentences.

    Each index points to the start of a new sentence (after the space
    following sentence-ending punctuation). Punctuation inside quotes
    is not treated as a boundary.
    """
    boundaries = []
    in_quotes = False
    i = 0
    length = len(text)

    while i < length:
        ch = text[i]

        # Toggle quote state on any quote character
        if ch in '"\u201c\u201d':
            in_quotes = not in_quotes
            i += 1
            continue

        # Only consider sentence-ending punctuation outside quotes
        if not in_quotes and ch in ".!?":
            # Skip ellipses (2+ dots in a row)
            if ch == "." and i + 1 < length and text[i + 1] == ".":
                while i < length and text[i] == ".":
                    i += 1
                continue

            # Check if followed by a space then a non-space (new sentence)
            if i + 1 < length and text[i + 1] == " " and i + 2 < length:
                boundaries.append(i + 2)

        i += 1

    return boundaries


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
    if len(text) <= max_chars:
        return [text]

    boundaries = _find_sentence_boundaries(text)
    if not boundaries:
        return [text]

    # Split points include start, each boundary, and end
    splits = [0, *boundaries, len(text)]
    chunks = []
    current_start = 0

    for i in range(1, len(splits)):
        end = splits[i]
        candidate = text[current_start:end].rstrip()

        if len(candidate) > max_chars and current_start != splits[i - 1]:
            # This sentence would push us over — flush what we have so far
            chunk = text[current_start : splits[i - 1]].rstrip()
            if chunk:
                chunks.append(chunk)
            current_start = splits[i - 1]

    # Flush remaining
    remaining = text[current_start:].rstrip()
    if remaining:
        chunks.append(remaining)

    return chunks if chunks else [text]


def parse_chapter(
    cleaned_path: Path,
    chapter_number: int,
    title: str,
    pov_character: str | None = None,
    subchapter: int | None = None,
) -> Chapter:
    """Parse a cleaned chapter file into a Chapter with typed segments.

    Extracts the chapter header from the first line, then stitches the
    remaining text into a continuous block (double newlines in cleaned
    files are page break artifacts). Dialogue is extracted at quote
    boundaries and long narration is split at sentence boundaries.

    Args:
        cleaned_path: Path to the cleaned chapter .txt file.
        chapter_number: Chapter number from the manifest.
        title: Chapter title from the manifest.
        pov_character: POV character name (from manifest), or None.
        subchapter: Sub-chapter index when the source splits a publisher
            chapter on `N.M` POV markers, else None.

    Returns:
        A Chapter instance with its segments tuple populated.
        Speaker field on segments is None at this stage.
    """
    text = cleaned_path.read_text(encoding="utf-8").strip()
    segments: list[Segment] = []
    seg_index = 0

    # Extract chapter header from the first line
    first_newline = text.find("\n")
    if first_newline == -1:
        # Single-line file — treat as header only
        first_line = text
        body = ""
    else:
        first_line = text[:first_newline].strip()
        body = text[first_newline:].strip()

    if _is_chapter_header(first_line):
        segments.append(
            Segment(
                index=seg_index,
                segment_type=SegmentType.CHAPTER_HEADER,
                text=first_line,
            )
        )
        seg_index += 1
    else:
        # No header detected — include first line in body
        body = text

    if not body:
        return Chapter(
            chapter_number=chapter_number,
            subchapter=subchapter,
            title=title,
            source_file=cleaned_path.name,
            pov_character=pov_character,
            segments=tuple(segments),
        )

    # Stitch body into continuous text — double newlines are page break artifacts
    body = re.sub(r"\s*\n\s*", " ", body).strip()

    # Extract dialogue/narration and split long narration chunks
    sub_segments = _extract_segments(body)
    for sub_type, sub_text in sub_segments:
        if sub_type == SegmentType.NARRATION and len(sub_text) > MAX_SEGMENT_CHARS:
            for chunk in split_long_narration(sub_text, MAX_SEGMENT_CHARS):
                segments.append(
                    Segment(
                        index=seg_index,
                        segment_type=SegmentType.NARRATION,
                        text=chunk,
                    )
                )
                seg_index += 1
        else:
            segments.append(
                Segment(
                    index=seg_index,
                    segment_type=sub_type,
                    text=sub_text,
                )
            )
            seg_index += 1

    return Chapter(
        chapter_number=chapter_number,
        subchapter=subchapter,
        title=title,
        source_file=cleaned_path.name,
        pov_character=pov_character,
        segments=tuple(segments),
    )
