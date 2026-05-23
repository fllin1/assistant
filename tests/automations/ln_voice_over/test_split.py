"""Tests for Stage 1: SPLIT — sub-chapter subdivision on `N.M` markers.

Focuses on the Phase-D subdivision logic that detects narrator-shifting
sub-chapters inside a publisher "chapter" (e.g. CoTE chapter 7 contains
`7.1`, `7.2`, `7.3`, `7.4` on bare lines). Main-chapter splitting is
already exercised indirectly through other pipeline tests; these cases
target the new guard rules.
"""

from pathlib import Path

from automations.ln_voice_over.split import (
    _subdivide_by_subchapter,
    chapter_id,
    normalize_chapter_arg,
    split_volume,
)


class TestSubdivideBySubchapter:
    def test_no_markers_returns_single_entry(self):
        text = "Just narration, no sub-chapter markers anywhere.\n"
        result = _subdivide_by_subchapter(text, chapter_number=5)
        assert result == [(None, text)]

    def test_two_markers_split_cleanly(self):
        text = "\n".join(
            [
                "7.1",
                "",
                "Body of sub one.",
                "",
                "7.2",
                "",
                "Body of sub two.",
                "",
            ]
        )
        result = _subdivide_by_subchapter(text, chapter_number=7)
        assert len(result) == 2
        assert result[0][0] == 1
        assert "Body of sub one" in result[0][1]
        assert "Body of sub two" not in result[0][1]
        assert result[1][0] == 2
        assert "Body of sub two" in result[1][1]

    def test_lead_in_before_first_marker_becomes_sub_zero(self):
        text = "\n".join(
            [
                "Chapter 6: Each and Every Calculation",
                "",
                "Lead-in narration that comes before any sub-chapter marker.",
                "",
                "6.1",
                "",
                "Body after first marker.",
                "",
                "6.2",
                "",
                "Body after second marker.",
                "",
            ]
        )
        result = _subdivide_by_subchapter(text, chapter_number=6)
        assert len(result) == 3
        assert result[0][0] == 0
        assert "Chapter 6: Each and Every Calculation" in result[0][1]
        assert "Lead-in narration" in result[0][1]
        assert "Body after first marker" not in result[0][1]
        assert result[1][0] == 1
        assert "Body after first marker" in result[1][1]
        assert "Lead-in narration" not in result[1][1]
        assert result[2][0] == 2
        assert "Body after second marker" in result[2][1]

    def test_no_lead_in_skips_sub_zero(self):
        text = "\n".join(
            [
                "7.1",
                "",
                "Body one.",
                "",
                "7.2",
                "",
                "Body two.",
                "",
            ]
        )
        result = _subdivide_by_subchapter(text, chapter_number=7)
        assert [minor for minor, _ in result] == [1, 2]

    def test_lone_marker_is_narrative_not_boundary(self):
        text = "\n".join(
            [
                "A reference to section 7.1 in the narration.",
                "",
                "7.1",
                "",
                "More body text — but no 7.2 ever appears.",
                "",
            ]
        )
        result = _subdivide_by_subchapter(text, chapter_number=7)
        assert result == [(None, text)]

    def test_stray_major_inside_another_chapter_ignored(self):
        text = "\n".join(
            [
                "7.1",
                "",
                "Body one.",
                "",
                "4.2",  # wrong major — ignored
                "",
                "Still body one continues.",
                "",
                "7.2",
                "",
                "Body two.",
                "",
            ]
        )
        result = _subdivide_by_subchapter(text, chapter_number=7)
        assert len(result) == 2
        assert "4.2" in result[0][1]

    def test_non_monotonic_rejects_subdivision(self, caplog):
        text = "\n".join(
            [
                "7.2",
                "",
                "Body two.",
                "",
                "7.1",
                "",
                "Body one.",
                "",
            ]
        )
        result = _subdivide_by_subchapter(text, chapter_number=7)
        assert result == [(None, text)]

    def test_four_markers_produce_four_entries(self):
        text = "\n".join(
            [
                "7.1",
                "",
                "a",
                "",
                "7.2",
                "",
                "b",
                "",
                "7.3",
                "",
                "c",
                "",
                "7.4",
                "",
                "d",
                "",
            ]
        )
        result = _subdivide_by_subchapter(text, chapter_number=7)
        assert [minor for minor, _ in result] == [1, 2, 3, 4]


class TestChapterId:
    def test_plain_chapter(self):
        assert chapter_id({"number": 7}) == "07"

    def test_subchapter(self):
        assert chapter_id({"number": 7, "subchapter": 1}) == "07_1"

    def test_subchapter_none_treated_as_plain(self):
        assert chapter_id({"number": 12, "subchapter": None}) == "12"


class TestNormalizeChapterArg:
    def test_pads_single_digit(self):
        assert normalize_chapter_arg("7") == "07"

    def test_preserves_two_digits(self):
        assert normalize_chapter_arg("12") == "12"

    def test_pads_with_letter_suffix(self):
        assert normalize_chapter_arg("4b") == "04b"

    def test_pads_with_subchapter_suffix(self):
        assert normalize_chapter_arg("7_1") == "07_1"


class TestSplitVolumeJsonWithSubchapters:
    def test_split_json_emits_subchapter_entries(self, tmp_path: Path):
        import json

        book_json = tmp_path / "book.json"
        book_json.write_text(
            json.dumps(
                {
                    "chapters": [
                        {"title": "Chapter 1", "text": "Intro text."},
                        {
                            "title": "Chapter 2",
                            "text": "\n2.1\n\nFirst.\n\n2.2\n\nSecond.\n",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        output_dir = tmp_path / "chapters"
        manifest = split_volume(book_json, output_dir)
        assert len(manifest) == 3
        assert manifest[0]["file"] == "chapter_01.txt"
        assert manifest[0]["narrator_status"] == "unset"
        assert manifest[0]["narrator"] is None
        assert "subchapter" not in manifest[0] or manifest[0].get("subchapter") is None
        assert manifest[1]["file"] == "chapter_02_1.txt"
        assert manifest[1]["subchapter"] == 1
        assert manifest[1]["narrator_status"] == "unset"
        assert manifest[1]["narrator"] is None
        assert manifest[2]["file"] == "chapter_02_2.txt"
        assert manifest[2]["subchapter"] == 2
        assert manifest[2]["narrator_status"] == "unset"
        assert manifest[2]["narrator"] is None
        assert (output_dir / "chapter_02_1.txt").exists()
        assert (output_dir / "chapter_02_2.txt").exists()
