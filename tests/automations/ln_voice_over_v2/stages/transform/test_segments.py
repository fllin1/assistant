"""Segment emission tests for the transform stage."""

from __future__ import annotations

import unicodedata

from automations.ln_voice_over_v2.stages.transform.chapters import ChapterSplit, UnitSlice
from automations.ln_voice_over_v2.stages.transform.contracts import ChapterIndexEntry
from automations.ln_voice_over_v2.stages.transform.segments import build_segment_files


def _split(
    chapter_number: int,
    slices: tuple[UnitSlice, ...],
) -> ChapterSplit:
    chapter_id = f"chapter_{chapter_number:02d}"
    return ChapterSplit(
        index_entry=ChapterIndexEntry(
            chapter_id=chapter_id,
            order=chapter_number - 1,
            segments_file=f"segments/{chapter_id}.json",
            display_name=f"Chapter {chapter_number}",
        ),
        slices=slices,
    )


def _slice(index: int, text: str, *, needs_review: bool = False) -> UnitSlice:
    return UnitSlice(
        text_unit_id=f"unit_{index:06d}",
        text=text,
        needs_review=needs_review,
    )


def _build(*splits: ChapterSplit):
    return build_segment_files(tuple(splits), "series-one", "v1")


def test_cross_page_narration_merge() -> None:
    segment_files = _build(
        _split(
            1,
            (
                _slice(5, "First page "),
                _slice(6, "second page."),
            ),
        )
    )

    segments = segment_files[0].segments

    assert len(segments) == 1
    assert segments[0].text == "First page second page."
    assert segments[0].source_unit_ids == ("unit_000005", "unit_000006")


def test_needs_review_boundary_blocks_merge() -> None:
    segment_files = _build(
        _split(
            1,
            (
                _slice(1, "Before."),
                _slice(2, "", needs_review=True),
                _slice(3, "After."),
            ),
        )
    )

    segments = segment_files[0].segments

    assert [segment.text for segment in segments] == [
        "Before.",
        "[needs_review:unit_000002]",
        "After.",
    ]
    assert segments[1].source_unit_ids == ("unit_000002",)
    assert segments[1].parser_hints == {"quote_candidate": False, "needs_review": True}


def test_empty_non_review_slice_is_skipped() -> None:
    segment_files = _build(
        _split(
            1,
            (
                _slice(1, "Visible text."),
                _slice(2, ""),
            ),
        )
    )

    segments = segment_files[0].segments

    assert len(segments) == 1
    assert segments[0].source_unit_ids == ("unit_000001",)


def test_segment_id_numbering_resets_per_chapter() -> None:
    segment_files = _build(
        _split(1, (_slice(1, "Chapter one."),)),
        _split(2, (_slice(2, "Chapter two."),)),
    )

    assert segment_files[0].segments[0].segment_id == "seg_000001"
    assert segment_files[1].segments[0].segment_id == "seg_000001"
    assert segment_files[0].segments[0].order == 0
    assert segment_files[1].segments[0].order == 0


def test_parser_hints_payloads_for_quote_and_narration() -> None:
    segment_files = _build(_split(1, (_slice(1, 'He said "Hi." Then left.'),)))

    segments = segment_files[0].segments

    assert segments[0].text == "He said"
    assert segments[0].parser_hints == {"quote_candidate": False}
    assert segments[1].text == '"Hi."'
    assert segments[1].parser_hints == {"quote_candidate": True, "quote_style": "ascii"}
    assert segments[2].text == "Then left."
    assert segments[2].parser_hints == {"quote_candidate": False}


def test_nfc_normalisation() -> None:
    decomposed = "Cafe\u0301"

    segment_files = _build(_split(1, (_slice(1, decomposed),)))
    emitted = segment_files[0].segments[0].text

    assert unicodedata.is_normalized("NFC", emitted)
    assert emitted == "Café"


def test_excessive_blank_lines_collapse() -> None:
    segment_files = _build(_split(1, (_slice(1, "A\n\n\n\nB"),)))

    assert segment_files[0].segments[0].text == "A\n\nB"


def test_unmatched_quote_run_emits_narration_with_flag() -> None:
    segment_files = _build(_split(1, (_slice(1, 'He said "Hi and walked away.'),)))

    segments = segment_files[0].segments

    assert len(segments) == 2
    assert segments[0].text == "He said"
    assert segments[0].parser_hints == {"quote_candidate": False}
    assert segments[1].text == '"Hi and walked away.'
    assert segments[1].parser_hints == {
        "quote_candidate": False,
        "quote_unmatched": True,
    }
