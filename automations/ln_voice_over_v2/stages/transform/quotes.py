"""Quote-aware tokenizer for the transform stage.

Pure functional helper: accepts a string, returns a tuple of tokens. The
caller (segments.py) decides how to lift tokens into `Segment` artifacts.
Glyphs are preserved verbatim — never folded to ASCII — because they are
structural signals downstream.
"""
# ruff: noqa: RUF001, RUF003

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final, Literal

logger = logging.getLogger("ln_voice_over_v2.transform.quotes")

TokenKind = Literal["narration", "quote"]
QuoteStyle = Literal["ascii", "curly", "single", "jp-square", "jp-double"]


@dataclass(frozen=True)
class Token:
    """A narration run or a quoted span produced by `tokenize`."""

    kind: TokenKind
    text: str
    quote_style: QuoteStyle | None = None
    quote_unmatched: bool = False


_STYLES: Final[dict[QuoteStyle, tuple[str, str]]] = {
    "ascii": ('"', '"'),
    "curly": ("“", "”"),
    "single": ("‘", "’"),
    "jp-square": ("「", "」"),
    "jp-double": ("『", "』"),
}


def tokenize(text: str) -> tuple[Token, ...]:
    """Walk `text` once and emit alternating narration and quote tokens.

    The single curly opener `'` only opens when preceded by whitespace or the
    start of the buffer so that mid-word apostrophes (it's) stay in
    narration. When an opener has no matching closer, the remainder of the
    text is emitted as a narration token with `quote_unmatched=True` and a
    `WARNING` is logged.
    """
    tokens: list[Token] = []
    pos = 0
    narration_start = 0
    n = len(text)

    while pos < n:
        opener_style = _detect_opener(text, pos)
        if opener_style is None:
            pos += 1
            continue

        if narration_start < pos:
            tokens.append(Token(kind="narration", text=text[narration_start:pos]))

        opener_glyph, closer_glyph = _STYLES[opener_style]
        body_start = pos + len(opener_glyph)
        closer_pos = text.find(closer_glyph, body_start)
        if closer_pos == -1:
            unmatched_text = text[pos:n]
            tokens.append(Token(kind="narration", text=unmatched_text, quote_unmatched=True))
            logger.warning("transform.quotes: unmatched %s opener at offset %d", opener_style, pos)
            return tuple(tokens)

        quote_end = closer_pos + len(closer_glyph)
        tokens.append(
            Token(
                kind="quote",
                text=text[pos:quote_end],
                quote_style=opener_style,
            )
        )
        pos = quote_end
        narration_start = pos

    if narration_start < n:
        tokens.append(Token(kind="narration", text=text[narration_start:n]))

    return tuple(tokens)


def _detect_opener(text: str, pos: int) -> QuoteStyle | None:
    ch = text[pos]
    if ch == '"':
        return "ascii"
    if ch == "“":
        return "curly"
    if ch == "「":
        return "jp-square"
    if ch == "『":
        return "jp-double"
    # Single curly only opens after whitespace or at the start of the buffer
    # so curly apostrophes inside words (don’t, it’s) stay in narration.
    if ch == "‘" and (pos == 0 or text[pos - 1].isspace()):
        return "single"
    return None
