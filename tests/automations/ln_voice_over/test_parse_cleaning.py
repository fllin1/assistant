"""Tests for the cleanup helpers inlined into parse (watermarks, page numbers, blank lines)."""

from automations.ln_voice_over.config import (
    INLINE_WATERMARK_PATTERNS,
    PAGE_NUMBER_PATTERNS,
    SCENE_BREAK_PATTERNS,
    WATERMARK_PATTERNS,
)
from automations.ln_voice_over.parse import (
    _collapse_blank_lines,
    _is_page_number,
    _is_scene_break,
    _is_watermark_line,
    _strip_inline_watermarks,
)


class TestStripInlineWatermarks:
    def test_strips_page_number_and_watermark_suffix(self):
        line = "He walked away. Page 1 Goldenagato | mp4directs.com"
        assert _strip_inline_watermarks(line, INLINE_WATERMARK_PATTERNS) == "He walked away."

    def test_strips_watermark_without_page_number(self):
        line = "She smiled. Goldenagato | mp4directs.com"
        assert _strip_inline_watermarks(line, INLINE_WATERMARK_PATTERNS) == "She smiled."

    def test_no_watermark_unchanged(self):
        line = "Just a normal sentence."
        assert _strip_inline_watermarks(line, INLINE_WATERMARK_PATTERNS) == line

    def test_multidigit_page_number(self):
        line = "End of text. Page 142 Goldenagato | mp4directs.com"
        assert _strip_inline_watermarks(line, INLINE_WATERMARK_PATTERNS) == "End of text."

    def test_empty_line(self):
        assert _strip_inline_watermarks("", INLINE_WATERMARK_PATTERNS) == ""


class TestIsWatermarkLine:
    def test_matches_standalone_goldenagato(self):
        assert _is_watermark_line("Goldenagato", WATERMARK_PATTERNS)

    def test_matches_standalone_mp4directs(self):
        assert _is_watermark_line("mp4directs.com", WATERMARK_PATTERNS)

    def test_matches_with_surrounding_whitespace(self):
        assert _is_watermark_line("  Goldenagato  ", WATERMARK_PATTERNS)

    def test_no_match_normal_text(self):
        assert not _is_watermark_line("She walked down the corridor.", WATERMARK_PATTERNS)

    def test_empty_line_not_watermark(self):
        assert not _is_watermark_line("", WATERMARK_PATTERNS)

    def test_case_sensitive(self):
        # "GOLDENAGATO" is not in the patterns (only "Goldenagato" and "goldenagato")
        assert not _is_watermark_line("GOLDENAGATO", WATERMARK_PATTERNS)


class TestIsPageNumber:
    def test_page_with_number(self):
        assert _is_page_number("  Page 42  ", PAGE_NUMBER_PATTERNS)

    def test_bare_number(self):
        assert _is_page_number("42", PAGE_NUMBER_PATTERNS)

    def test_bare_number_with_whitespace(self):
        assert _is_page_number("  123  ", PAGE_NUMBER_PATTERNS)

    def test_page_lowercase(self):
        assert _is_page_number("page 1", PAGE_NUMBER_PATTERNS)

    def test_page_with_extra_text_no_match(self):
        assert not _is_page_number("Page 42 of 300", PAGE_NUMBER_PATTERNS)

    def test_inline_page_reference_no_match(self):
        assert not _is_page_number("He was on page 42", PAGE_NUMBER_PATTERNS)

    def test_empty_line(self):
        assert not _is_page_number("", PAGE_NUMBER_PATTERNS)

    def test_chapter_header_no_match(self):
        assert not _is_page_number("Chapter 1", PAGE_NUMBER_PATTERNS)

    def test_number_with_dot_no_match(self):
        assert not _is_page_number("1.", PAGE_NUMBER_PATTERNS)


class TestIsSceneBreak:
    def test_asterisks(self):
        assert _is_scene_break("***", SCENE_BREAK_PATTERNS)

    def test_spaced_asterisks(self):
        assert _is_scene_break("  * * *  ", SCENE_BREAK_PATTERNS)

    def test_dashes(self):
        assert _is_scene_break("---", SCENE_BREAK_PATTERNS)

    def test_long_dashes(self):
        assert _is_scene_break("-----", SCENE_BREAK_PATTERNS)

    def test_diamonds(self):
        assert _is_scene_break("◇◆◇", SCENE_BREAK_PATTERNS)

    def test_inline_dashes_no_match(self):
        assert not _is_scene_break("some text---more text", SCENE_BREAK_PATTERNS)

    def test_partial_asterisks_no_match(self):
        assert not _is_scene_break("** not a break", SCENE_BREAK_PATTERNS)

    def test_regular_text(self):
        assert not _is_scene_break("Just a normal line.", SCENE_BREAK_PATTERNS)


class TestCollapseBlankLines:
    def test_three_blanks_collapsed_to_two(self):
        text = "a\n\n\n\nb"
        assert _collapse_blank_lines(text, 2) == "a\n\n\nb"

    def test_five_blanks_collapsed_to_two(self):
        text = "a\n\n\n\n\n\nb"
        assert _collapse_blank_lines(text, 2) == "a\n\n\nb"

    def test_two_blanks_unchanged(self):
        text = "a\n\n\nb"
        assert _collapse_blank_lines(text, 2) == "a\n\n\nb"

    def test_single_blank_unchanged(self):
        text = "a\n\nb"
        assert _collapse_blank_lines(text, 2) == "a\n\nb"

    def test_no_blanks_unchanged(self):
        text = "a\nb"
        assert _collapse_blank_lines(text, 2) == "a\nb"

    def test_custom_max_one(self):
        text = "a\n\n\nb"
        assert _collapse_blank_lines(text, 1) == "a\n\nb"

    def test_whitespace_only_lines_count_as_blank(self):
        text = "a\n   \n   \n   \nb"
        assert _collapse_blank_lines(text, 2) == "a\n   \n   \nb"
