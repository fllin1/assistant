"""Quote tokenizer tests for the transform stage."""
# ruff: noqa: RUF001

from __future__ import annotations

import logging

import pytest
from automations.ln_voice_over_v2.stages.transform.quotes import Token, tokenize


def test_ascii_quote_emits_narration_quote_narration() -> None:
    """ASCII quotes split into narration / quote / narration tokens."""
    tokens = tokenize('He said "Hello." She nodded.')

    assert tokens == (
        Token(kind="narration", text="He said "),
        Token(kind="quote", text='"Hello."', quote_style="ascii"),
        Token(kind="narration", text=" She nodded."),
    )


def test_curly_quote_emits_narration_then_quote() -> None:
    """Curly opener/closer pair produces a single curly-style quote token."""
    tokens = tokenize("He said “Hello.”")

    assert tokens == (
        Token(kind="narration", text="He said "),
        Token(kind="quote", text="“Hello.”", quote_style="curly"),
    )


def test_jp_square_quote_is_recognized() -> None:
    """Japanese square brackets 「」 form a jp-square quote span."""
    tokens = tokenize("彼は「こんにちは」と言った。")

    assert tokens == (
        Token(kind="narration", text="彼は"),
        Token(
            kind="quote",
            text="「こんにちは」",
            quote_style="jp-square",
        ),
        Token(kind="narration", text="と言った。"),
    )


def test_jp_double_quote_is_recognized() -> None:
    """Japanese double brackets 『』 form a jp-double quote span."""
    tokens = tokenize("本は『メモワール』です。")

    assert tokens == (
        Token(kind="narration", text="本は"),
        Token(
            kind="quote",
            text="『メモワール』",
            quote_style="jp-double",
        ),
        Token(kind="narration", text="です。"),
    )


def test_ascii_apostrophe_inside_word_stays_in_narration() -> None:
    """`it's` is one narration token; the ASCII apostrophe is not a quote glyph."""
    tokens = tokenize("It's a fine day.")

    assert tokens == (Token(kind="narration", text="It's a fine day."),)


def test_curly_apostrophe_inside_word_stays_in_narration() -> None:
    """Mid-word curly `'` is not treated as a single-quote opener."""
    tokens = tokenize("It’s a fine day.")

    assert tokens == (Token(kind="narration", text="It’s a fine day."),)


def test_single_curly_opener_after_whitespace_is_a_quote() -> None:
    """A curly `'` at start-of-buffer opens a single-style quote."""
    tokens = tokenize("‘Hello,’ she said.")

    assert tokens == (
        Token(kind="quote", text="‘Hello,’", quote_style="single"),
        Token(kind="narration", text=" she said."),
    )


def test_nested_quotes_emit_outer_only() -> None:
    """An inner ASCII apostrophe pair is preserved literally inside an outer quote."""
    tokens = tokenize("\"He said, 'no.'\"")

    assert tokens == (Token(kind="quote", text="\"He said, 'no.'\"", quote_style="ascii"),)


def test_unmatched_open_demotes_to_narration_with_flag(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unmatched opener demotes the remainder to narration with quote_unmatched=True."""
    with caplog.at_level(logging.WARNING, logger="ln_voice_over_v2.transform.quotes"):
        tokens = tokenize('He said "Hello and walked away.')

    assert tokens == (
        Token(kind="narration", text="He said "),
        Token(
            kind="narration",
            text='"Hello and walked away.',
            quote_unmatched=True,
        ),
    )
    assert any("unmatched" in record.message for record in caplog.records)


def test_multi_paragraph_quote_preserves_internal_blank_line() -> None:
    """A quote span spanning a blank line is one token with the newlines intact."""
    tokens = tokenize('"Para 1.\n\nPara 2."')

    assert tokens == (Token(kind="quote", text='"Para 1.\n\nPara 2."', quote_style="ascii"),)
