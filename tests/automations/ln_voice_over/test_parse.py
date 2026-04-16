"""Tests for Stage 3: PARSE — structural segmentation of chapter text."""

from pathlib import Path

from automations.ln_voice_over.models import SegmentType
from automations.ln_voice_over.parse import (
    _extract_segments,
    parse_chapter,
    split_long_narration,
)


class TestExtractSegments:
    def test_pure_narration(self):
        result = _extract_segments("He walked down the hall.")
        assert result == [(SegmentType.NARRATION, "He walked down the hall.")]

    def test_pure_dialogue(self):
        result = _extract_segments('"Hello there."')
        assert result == [(SegmentType.DIALOGUE, '"Hello there."')]

    def test_inline_dialogue_extracted(self):
        text = 'She looked around. "Good morning." The class nodded.'
        result = _extract_segments(text)
        assert len(result) == 3
        assert result[0] == (SegmentType.NARRATION, "She looked around.")
        assert result[1] == (SegmentType.DIALOGUE, '"Good morning."')
        assert result[2] == (SegmentType.NARRATION, "The class nodded.")

    def test_multiple_dialogue_blocks(self):
        text = '"Hello," she said. "How are you?"'
        result = _extract_segments(text)
        types = [t for t, _ in result]
        assert types.count(SegmentType.DIALOGUE) == 2

    def test_dialogue_at_start(self):
        text = '"Good morning." She smiled.'
        result = _extract_segments(text)
        assert result[0][0] == SegmentType.DIALOGUE
        assert result[1][0] == SegmentType.NARRATION

    def test_dialogue_at_end(self):
        text = 'She whispered, "Goodbye."'
        result = _extract_segments(text)
        assert result[0][0] == SegmentType.NARRATION
        assert result[1][0] == SegmentType.DIALOGUE

    def test_curly_quotes(self):
        text = "He said, \u201cNice to meet you.\u201d"
        result = _extract_segments(text)
        dialogue_parts = [t for t, _ in result if t == SegmentType.DIALOGUE]
        assert len(dialogue_parts) == 1

    def test_no_quotes(self):
        text = "The wind howled outside."
        result = _extract_segments(text)
        assert result == [(SegmentType.NARRATION, "The wind howled outside.")]

    def test_empty_parts_skipped(self):
        text = '"First line." "Second line."'
        result = _extract_segments(text)
        for _seg_type, seg_text in result:
            assert seg_text.strip()


class TestSplitLongNarration:
    def test_short_text_returns_single(self):
        assert split_long_narration("Short text.", 500) == ["Short text."]

    def test_splits_at_sentence_boundary(self):
        text = "First sentence. Second sentence. Third sentence."
        chunks = split_long_narration(text, 35)
        assert len(chunks) >= 2
        assert all(c.strip() for c in chunks)
        assert " ".join(chunks) == text

    def test_respects_max_chars(self):
        text = "A short one. " + "This is a medium-length sentence here. " * 10
        chunks = split_long_narration(text, 100)
        for chunk in chunks[:-1]:
            assert len(chunk) <= 120

    def test_single_long_sentence_kept_whole(self):
        text = "A" * 600
        assert split_long_narration(text, 500) == [text]

    def test_dialogue_quotes_not_split(self):
        text = 'She said "Good morning. Everyone here?" and left. He nodded.'
        chunks = split_long_narration(text, 55)
        found_dialogue = any('"Good morning. Everyone here?"' in c for c in chunks)
        assert found_dialogue

    def test_ellipses_not_treated_as_boundary(self):
        text = "He paused... Then he continued walking. The road was long."
        chunks = split_long_narration(text, 45)
        found_ellipsis = any("paused..." in c for c in chunks)
        assert found_ellipsis

    def test_empty_text(self):
        assert split_long_narration("", 500) == [""]

    def test_exact_max_chars(self):
        text = "Hello world."
        assert split_long_narration(text, len(text)) == [text]


class TestParseChapter:
    def test_chapter_header_extracted(self, tmp_path: Path):
        chapter_file = tmp_path / "chapter.txt"
        chapter_file.write_text(
            "Chapter 1: The Beginning\n\nHe walked in.\n",
            encoding="utf-8",
        )

        chapter = parse_chapter(chapter_file, 1, "The Beginning")

        assert chapter.segments[0].segment_type == SegmentType.CHAPTER_HEADER
        assert chapter.segments[0].text == "Chapter 1: The Beginning"

    def test_inline_dialogue_extracted(self, tmp_path: Path):
        chapter_file = tmp_path / "chapter.txt"
        chapter_file.write_text(
            'Chapter 1: Test\n\nShe looked around. "Good morning." The class nodded.\n',
            encoding="utf-8",
        )

        chapter = parse_chapter(chapter_file, 1, "Test")

        types = [s.segment_type for s in chapter.segments]
        assert SegmentType.DIALOGUE in types
        dialogue_segs = [s for s in chapter.segments if s.segment_type == SegmentType.DIALOGUE]
        assert dialogue_segs[0].text == '"Good morning."'

    def test_double_newlines_stitched(self, tmp_path: Path):
        # Simulates a page break artifact: mid-sentence double newline
        chapter_file = tmp_path / "chapter.txt"
        chapter_file.write_text(
            "Chapter 1: Test\n\nHe walked as far as only\n\nthree people could.\n",
            encoding="utf-8",
        )

        chapter = parse_chapter(chapter_file, 1, "Test")

        # Body should be stitched — "only" and "three" joined
        narration = [s for s in chapter.segments if s.segment_type == SegmentType.NARRATION]
        full_text = " ".join(s.text for s in narration)
        assert "only three" in full_text

    def test_long_narration_splits(self, tmp_path: Path):
        long_text = "This is a sentence. " * 40
        chapter_file = tmp_path / "chapter.txt"
        chapter_file.write_text(
            f"Chapter 1: Test\n\n{long_text}\n",
            encoding="utf-8",
        )

        chapter = parse_chapter(chapter_file, 1, "Test")

        narration_segments = [
            s for s in chapter.segments if s.segment_type == SegmentType.NARRATION
        ]
        assert len(narration_segments) > 1

    def test_segments_have_incrementing_indices(self, tmp_path: Path):
        chapter_file = tmp_path / "chapter.txt"
        chapter_file.write_text(
            'Chapter 1: Test\n\n"Hello," she said. "Goodbye."\n',
            encoding="utf-8",
        )

        chapter = parse_chapter(chapter_file, 1, "Test")

        indices = [s.index for s in chapter.segments]
        assert indices == list(range(len(chapter.segments)))

    def test_pov_character_flows_through(self, tmp_path: Path):
        chapter_file = tmp_path / "chapter.txt"
        chapter_file.write_text("Chapter 1: Test\n\nSome text.\n", encoding="utf-8")

        chapter = parse_chapter(chapter_file, 1, "Test", pov_character="Ayanokouji")

        assert chapter.pov_character == "Ayanokouji"

    def test_speaker_is_none(self, tmp_path: Path):
        chapter_file = tmp_path / "chapter.txt"
        chapter_file.write_text("Chapter 1: Test\n\nSome text.\n", encoding="utf-8")

        chapter = parse_chapter(chapter_file, 1, "Test")

        for segment in chapter.segments:
            assert segment.speaker is None

    def test_no_header_detected(self, tmp_path: Path):
        chapter_file = tmp_path / "chapter.txt"
        chapter_file.write_text("Just some text without a header.\n", encoding="utf-8")

        chapter = parse_chapter(chapter_file, 1, "Test")

        types = [s.segment_type for s in chapter.segments]
        assert SegmentType.CHAPTER_HEADER not in types
        assert SegmentType.NARRATION in types
