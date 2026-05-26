"""Tests for prepare-stage OCR refusal detection."""

from __future__ import annotations

import pytest
from automations.ln_voice_over_v2.stages.prepare.ocr import (
    OcrPageResult,
    _is_failed_ocr,
    _looks_like_refusal,
)

HISTORICAL_REFUSALS = [
    "Sorry, I can’t provide a full-page verbatim transcription of copyrighted text "
    "from the image.",
    "Sorry, I can’t provide a full verbatim transcription of this page.",
    "I can’t provide a full OCR transcription of this copyrighted book page. I can "
    "summarize it or transcribe a short excerpt.",
    "Sorry, I can’t provide a full-page verbatim transcript of copyrighted text from "
    "the image. I can provide a short excerpt or a summary instead.",
    "Sorry, I can’t provide a full verbatim OCR transcript of this copyrighted page. "
    "I can transcribe a short excerpt or summarize the page.",
]


@pytest.mark.parametrize("transcript", HISTORICAL_REFUSALS)
def test_looks_like_refusal_matches_historical_refusals(transcript: str) -> None:
    """The five observed refusal transcripts are classified as recoverable failures."""
    assert _looks_like_refusal(transcript) is True


def test_looks_like_refusal_rejects_body_prose() -> None:
    """Ordinary body prose is not classified by length or vocabulary heuristics."""
    transcript = (
        "The classroom had settled into the kind of quiet that made every small sound "
        "seem deliberate. Desks scraped, notebooks opened, and the rain outside tapped "
        "against the windows with a rhythm that refused to match the clock. I watched "
        "the teacher write the next assignment on the board while trying to decide "
        "whether the expression on Horikita's face meant irritation or concentration. "
        "Across the aisle, Sudou leaned back too far in his chair and caught himself "
        "before anyone could scold him. No one said much, but the room was full of "
        "messages: glances exchanged, questions postponed, small calculations hidden "
        "behind ordinary morning routines. By the time the bell rang, the problem had "
        "already moved from the board into everyone's plans for the day, and pretending "
        "otherwise would only make the next conversation harder. I packed my textbook "
        "slowly enough to watch the others leave in groups, each one choosing a route "
        "that revealed more than they intended. The ordinary hallway noise returned at "
        "once, but the atmosphere had shifted. Someone would bring up the assignment "
        "before lunch, someone else would deny caring, and the people who cared most "
        "would say the least until they had an advantage."
    )

    assert _looks_like_refusal(transcript) is False


def test_looks_like_refusal_rejects_mid_string_dialogue_sorry_but() -> None:
    """A dialogue line containing the refusal phrase mid-string is allowed."""
    transcript = (
        "Kei folded her arms and looked toward the window before answering. "
        '"Sorry, but I can’t come with you today," she said, as if the decision had '
        "already cost her more than she wanted to admit."
    )

    assert _looks_like_refusal(transcript) is False


def test_looks_like_refusal_rejects_short_chapter_break() -> None:
    """Short legitimate page text does not become a refusal by being short."""
    assert _looks_like_refusal("Page 59\ngito | mp4directs.com") is False


@pytest.mark.parametrize(
    "transcript",
    [
        "",
        "   \n\n  ",
        "As an example, this sentence starts similarly but is ordinary prose.",
    ],
)
def test_looks_like_refusal_rejects_edge_controls(transcript: str) -> None:
    """Empty, whitespace, and non-refusal prefixes stay outside the regex."""
    assert _looks_like_refusal(transcript) is False


def test_is_failed_ocr_refusal_sentence_non_illustration() -> None:
    """A refusal transcript is a failed OCR attempt on a normal page."""
    result = OcrPageResult(
        transcript="Sorry, I can't provide a full verbatim transcription of this page.",
        is_illustration=False,
    )

    assert _is_failed_ocr(result) is True


def test_is_failed_ocr_refusal_sentence_illustration() -> None:
    """A refusal transcript is failed OCR regardless of the illustration flag."""
    result = OcrPageResult(transcript="Sorry, I can't do that.", is_illustration=True)

    assert _is_failed_ocr(result) is True


def test_is_failed_ocr_empty_non_illustration_sentinel() -> None:
    """An empty transcript on a non-illustration page is the structural sentinel."""
    result = OcrPageResult(transcript="", is_illustration=False)

    assert _is_failed_ocr(result) is True


def test_is_failed_ocr_empty_illustration_success() -> None:
    """A full-bleed illustration legitimately has an empty transcript."""
    result = OcrPageResult(transcript="", is_illustration=True)

    assert _is_failed_ocr(result) is False


def test_is_failed_ocr_plain_text_success() -> None:
    """Ordinary text on an ordinary page is successful OCR."""
    result = OcrPageResult(transcript="some real body text", is_illustration=False)

    assert _is_failed_ocr(result) is False


def test_is_failed_ocr_mixed_illustration_text_success() -> None:
    """Text on an illustration spread is still a valid OCR result."""
    result = OcrPageResult(transcript="some real body text", is_illustration=True)

    assert _is_failed_ocr(result) is False


def test_is_failed_ocr_whitespace_only_non_illustration_success() -> None:
    """Whitespace-only text is not normalized into the structural sentinel."""
    result = OcrPageResult(transcript="   ", is_illustration=False)

    assert _is_failed_ocr(result) is False
