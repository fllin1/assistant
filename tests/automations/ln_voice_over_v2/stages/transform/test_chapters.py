"""Chapter detection tests for the transform stage."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from automations.ln_voice_over_v2.series.contracts import StoryProfile
from automations.ln_voice_over_v2.stages.prepare.contracts import PreparedTextUnit
from automations.ln_voice_over_v2.stages.transform.chapters import (
    PACKAGED_DEFAULT_STORY_PROFILE,
    detect_chapters,
    load_story_profile,
    resolve_story_profile_path,
)


@pytest.fixture
def default_profile() -> StoryProfile:
    return load_story_profile(PACKAGED_DEFAULT_STORY_PROFILE)


def _unit(index: int, text: str, *, needs_review: bool = False) -> PreparedTextUnit:
    return PreparedTextUnit(
        text_unit_id=f"unit_{index:06d}",
        order=index,
        text=text,
        source_path=f"source/pages/{index + 1:03d}.png",
        source_locator={"page": index + 1},
        needs_review=needs_review,
    )


def _subchapter_profile() -> StoryProfile:
    return StoryProfile(
        schema_version=1,
        profile_id="subchapter-story",
        display_name="Subchapter Story",
        rules={
            "chapter_headings": ["^\\s*Chapter\\s+(?P<num>\\d+(?:\\.\\d+)?)\\b"],
        },
    )


def test_heading_at_page_top_assigns_whole_page_to_new_chapter(
    default_profile: StoryProfile,
) -> None:
    """A heading at offset 0 of a page yields a slice equal to the entire page."""
    units = (
        _unit(0, "Prologue\nThe corridor was quiet."),
        _unit(1, "Chapter 1\nFresh prose for the new chapter."),
    )

    splits = detect_chapters(units, default_profile)

    assert [split.index_entry.display_name for split in splits] == ["Prologue", "Chapter 1"]
    assert splits[0].slices[0].text == "Prologue\nThe corridor was quiet."
    assert splits[0].slices[0].text_unit_id == "unit_000000"
    assert splits[1].slices[0].text == "Chapter 1\nFresh prose for the new chapter."
    assert splits[1].slices[0].text_unit_id == "unit_000001"


def test_mid_page_heading_splits_text_with_shared_text_unit_id(
    default_profile: StoryProfile,
) -> None:
    """A mid-page heading attaches the pre-heading slice to the prior chapter."""
    units = (
        _unit(0, "Prologue\nIntro line."),
        _unit(1, "Tail of prologue.\nChapter 1\nNew chapter prose."),
    )

    splits = detect_chapters(units, default_profile)

    assert len(splits) == 2
    prologue, chapter_one = splits

    assert [s.text_unit_id for s in prologue.slices] == ["unit_000000", "unit_000001"]
    assert prologue.slices[0].text == "Prologue\nIntro line."
    assert prologue.slices[1].text == "Tail of prologue.\n"

    assert [s.text_unit_id for s in chapter_one.slices] == ["unit_000001"]
    assert chapter_one.slices[0].text == "Chapter 1\nNew chapter prose."
    assert chapter_one.index_entry.display_name == "Chapter 1"
    assert chapter_one.index_entry.chapter_id == "chapter_01"


def test_multiple_headings_on_one_page_split_recursively(
    default_profile: StoryProfile,
) -> None:
    """Two headings on a single page produce two chapters from that page."""
    units = (_unit(0, "Prologue\nText A\nChapter 1\nText B"),)

    splits = detect_chapters(units, default_profile)

    assert len(splits) == 2
    assert splits[0].index_entry.display_name == "Prologue"
    assert splits[0].slices[0].text == "Prologue\nText A\n"
    assert splits[1].index_entry.display_name == "Chapter 1"
    assert splits[1].slices[0].text == "Chapter 1\nText B"


def test_no_heading_falls_back_to_single_chapter(
    default_profile: StoryProfile, caplog: pytest.LogCaptureFixture
) -> None:
    """A heading-less volume becomes a single chapter_01 fallback with a warning."""
    units = (
        _unit(0, "Plain prose page one."),
        _unit(1, "Plain prose page two."),
    )

    with caplog.at_level(logging.WARNING, logger="ln_voice_over_v2.transform.chapters"):
        splits = detect_chapters(units, default_profile)

    assert len(splits) == 1
    entry = splits[0].index_entry
    assert entry.chapter_id == "chapter_01"
    assert entry.order == 0
    assert entry.segments_file == "segments/chapter_01.json"
    assert entry.display_name == "Chapter 1"
    assert [s.text_unit_id for s in splits[0].slices] == ["unit_000000", "unit_000001"]
    assert any("no chapter heading matched" in record.message for record in caplog.records)


def test_subchapter_numbering_from_fractional_num(
    default_profile: StoryProfile,
) -> None:
    """'Chapter 7.1' produces chapter_07_1 with the literal display name."""
    units = (_unit(0, "Chapter 7.1\nProse for the subchapter."),)

    splits = detect_chapters(units, default_profile)

    assert len(splits) == 1
    assert splits[0].index_entry.chapter_id == "chapter_07_1"
    assert splits[0].index_entry.display_name == "Chapter 7.1"


def test_detects_bare_numeric_subchapter_markers_automatically() -> None:
    """Bare numeric markers split automatically inside their chapter scope."""
    units = (
        _unit(
            0,
            (
                "Chapter 5: Under Siege\nOpening narration.\n"
                "5.1\nKiriyama section.\n"
                "5.2\nKouenji section."
            ),
        ),
    )

    splits = detect_chapters(units, _subchapter_profile())

    assert [split.index_entry.chapter_id for split in splits] == [
        "chapter_05",
        "chapter_05_1",
        "chapter_05_2",
    ]
    assert [split.index_entry.display_name for split in splits] == [
        "Chapter 5: Under Siege",
        "5.1",
        "5.2",
    ]
    assert splits[1].slices[0].text == "5.1\nKiriyama section.\n"


def test_detects_ocr_glued_numeric_subchapter_markers_automatically() -> None:
    """OCR/page-source glue before a marker does not hide the subchapter split."""
    units = (
        _unit(
            0,
            (
                "Chapter 6: Each and Every Calculation\nOpening narration. "
                "Page 159 Goldenagato | mp4directs.com6.2  "
                "I NOTICED SOMETHING UNUSUAL around seven o'clock."
            ),
        ),
    )

    splits = detect_chapters(units, _subchapter_profile())

    assert [split.index_entry.chapter_id for split in splits] == [
        "chapter_06",
        "chapter_06_2",
    ]
    assert splits[1].index_entry.display_name == "6.2"
    assert splits[0].slices[0].text.endswith("Page 159 Goldenagato | mp4directs.com")
    assert splits[1].slices[0].text.startswith("6.2  I NOTICED")


def test_bare_numeric_markers_ignored_without_matching_chapter_anchor() -> None:
    """Automatic numeric markers must match a preceding numbered chapter."""
    units = (
        _unit(
            0,
            (
                "Chapter 6: Each and Every Calculation\nOpening narration. "
                "This is version 7.2 of the school document, not a subchapter."
            ),
        ),
    )

    splits = detect_chapters(units, _subchapter_profile())

    assert [split.index_entry.chapter_id for split in splits] == ["chapter_06"]


def test_bare_numeric_markers_ignored_after_different_chapter_anchor() -> None:
    """A previous chapter base does not authorize later mismatched markers."""
    units = (
        _unit(
            0,
            (
                "Chapter 6\nEarlier section.\n"
                "Chapter 7\nLater section mentions legacy note 6.2 but stays chapter seven."
            ),
        ),
    )

    splits = detect_chapters(units, _subchapter_profile())

    assert [split.index_entry.chapter_id for split in splits] == ["chapter_06", "chapter_07"]


def test_display_name_appends_subtitle_when_heading_ends_with_colon(
    default_profile: StoryProfile,
) -> None:
    units = (_unit(0, "Chapter 1:\nAmasawa Ichika's Soliloquy\n\nBody."),)

    splits = detect_chapters(units, default_profile)

    assert splits[0].index_entry.display_name == "Chapter 1: Amasawa Ichika's Soliloquy"


def test_display_name_unchanged_when_subtitle_already_inline(
    default_profile: StoryProfile,
) -> None:
    units = (_unit(0, "Chapter 1: Amasawa Ichika's Soliloquy\n\nBody."),)

    splits = detect_chapters(units, default_profile)

    assert splits[0].index_entry.display_name == "Chapter 1: Amasawa Ichika's Soliloquy"


def test_display_name_unchanged_when_no_trailing_colon(
    default_profile: StoryProfile,
) -> None:
    units = (_unit(0, "Chapter 1\nBody."),)

    splits = detect_chapters(units, default_profile)

    assert splits[0].index_entry.display_name == "Chapter 1"


def test_display_name_does_not_consume_next_heading_as_subtitle(
    default_profile: StoryProfile,
) -> None:
    units = (_unit(0, "Chapter 1:\nChapter 2:\nBody."),)

    splits = detect_chapters(units, default_profile)

    assert len(splits) == 2
    assert splits[0].index_entry.display_name == "Chapter 1:"
    assert [split.index_entry.chapter_id for split in splits] == ["chapter_01", "chapter_02"]


def test_front_matter_synthesized_when_first_match_is_numbered(
    default_profile: StoryProfile,
) -> None:
    units = (
        _unit(0, "Cover content."),
        _unit(1, "Chapter 1\nOpening."),
        _unit(2, "Chapter 2\nMiddle."),
    )

    splits = detect_chapters(units, default_profile)

    assert [split.index_entry.chapter_id for split in splits] == [
        "chapter_00",
        "chapter_01",
        "chapter_02",
    ]
    assert [split.index_entry.order for split in splits] == [0, 1, 2]
    assert splits[0].index_entry.display_name == "Front Matter"
    assert splits[0].index_entry.segments_file == "segments/chapter_00.json"
    assert [s.text_unit_id for s in splits[0].slices] == ["unit_000000"]
    assert splits[0].slices[0].text == "Cover content."


def test_no_front_matter_when_first_match_is_prologue(
    default_profile: StoryProfile,
) -> None:
    units = (
        _unit(0, "Prologue\nA quiet start."),
        _unit(1, "Chapter 1\nOpening."),
    )

    splits = detect_chapters(units, default_profile)

    assert [split.index_entry.chapter_id for split in splits] == ["chapter_00", "chapter_01"]
    assert [split.index_entry.display_name for split in splits] == ["Prologue", "Chapter 1"]


def test_no_front_matter_when_pre_text_empty(
    default_profile: StoryProfile,
) -> None:
    units = (_unit(0, "Chapter 1\nBody."),)

    splits = detect_chapters(units, default_profile)

    assert len(splits) == 1
    assert splits[0].index_entry.chapter_id == "chapter_01"
    assert splits[0].index_entry.display_name == "Chapter 1"


def test_prologue_chapter_epilogue_three_chapters(
    default_profile: StoryProfile,
) -> None:
    """Prologue + Chapter 2 + Epilogue keeps dense order and position-aware ids."""
    units = (
        _unit(0, "Prologue\nA quiet start."),
        _unit(1, "Chapter 2\nThe main body of the volume."),
        _unit(2, "Epilogue\nA quiet end."),
    )

    splits = detect_chapters(units, default_profile)

    assert [s.index_entry.order for s in splits] == [0, 1, 2]
    assert [s.index_entry.display_name for s in splits] == [
        "Prologue",
        "Chapter 2",
        "Epilogue",
    ]
    assert [s.index_entry.chapter_id for s in splits] == [
        "chapter_00",
        "chapter_02",
        "chapter_03",
    ]


def test_prologue_chapter_one_no_longer_collides(
    default_profile: StoryProfile,
) -> None:
    """Prologue + Chapter 1 + Epilogue maps to three unique chapter ids."""
    units = (
        _unit(0, "Prologue\nA quiet start."),
        _unit(1, "Chapter 1\nThe main body of the volume."),
        _unit(2, "Epilogue\nA quiet end."),
    )

    splits = detect_chapters(units, default_profile)

    assert [s.index_entry.display_name for s in splits] == [
        "Prologue",
        "Chapter 1",
        "Epilogue",
    ]
    assert [s.index_entry.chapter_id for s in splits] == [
        "chapter_00",
        "chapter_01",
        "chapter_02",
    ]
    assert len({s.index_entry.chapter_id for s in splits}) == len(splits)


def test_interlude_between_numbered_chapters_gets_subchapter_id(
    default_profile: StoryProfile,
) -> None:
    """A non-num heading between numbered chapters uses the previous chapter base."""
    units = (
        _unit(0, "Chapter 1\nOpening."),
        _unit(1, "Chapter 2\nMiddle."),
        _unit(2, "Interlude\nA pause."),
        _unit(3, "Chapter 3\nClosing."),
    )

    splits = detect_chapters(units, default_profile)

    assert [s.index_entry.chapter_id for s in splits] == [
        "chapter_01",
        "chapter_02",
        "chapter_02_1",
        "chapter_03",
    ]


def test_multiple_back_matter_headings_increment_past_max_num(
    default_profile: StoryProfile,
) -> None:
    """Back matter headings take slots after the highest numbered chapter."""
    units = (
        _unit(0, "Chapter 1\nOpening."),
        _unit(1, "Chapter 2\nMiddle."),
        _unit(2, "Epilogue\nA quiet end."),
        _unit(3, "Afterword\nA final note."),
    )

    splits = detect_chapters(units, default_profile)

    assert [s.index_entry.chapter_id for s in splits] == [
        "chapter_01",
        "chapter_02",
        "chapter_03",
        "chapter_04",
    ]


def test_multiple_front_matter_headings(
    default_profile: StoryProfile,
) -> None:
    """All non-num headings before the first numbered chapter count as front matter."""
    units = (
        _unit(0, "Prologue\nA quiet start."),
        _unit(1, "Interlude\nA prefatory pause."),
        _unit(2, "Chapter 1\nOpening."),
    )

    splits = detect_chapters(units, default_profile)

    assert [s.index_entry.chapter_id for s in splits] == [
        "chapter_00",
        "chapter_00_2",
        "chapter_01",
    ]


def test_no_numbered_chapter_keeps_legacy_ordinal_rule(
    default_profile: StoryProfile,
) -> None:
    """Volumes with headings but no captured num keep dense ordinal chapter ids."""
    units = (
        _unit(0, "Prologue\nA quiet start."),
        _unit(1, "Epilogue\nA quiet end."),
    )

    splits = detect_chapters(units, default_profile)

    assert [s.index_entry.chapter_id for s in splits] == ["chapter_01", "chapter_02"]


def test_per_series_override_beats_packaged_template(tmp_path: Path) -> None:
    """A per-series story_profile.json under <data_root>/<series>/config wins."""
    data_root = tmp_path / "projects"
    series = "series-one"
    override_dir = data_root / series / "config"
    override_dir.mkdir(parents=True)
    override_path = override_dir / "story_profile.json"
    override_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_id": "default",
                "display_name": "Override Story Profile",
                "rules": {
                    "chapter_headings": ["^### Section\\b"],
                },
            }
        ),
        encoding="utf-8",
    )

    resolved = resolve_story_profile_path(data_root, series)

    assert resolved == override_path


def test_packaged_template_resolves_when_no_override(tmp_path: Path) -> None:
    """Absence of a per-series override falls back to the packaged template."""
    resolved = resolve_story_profile_path(tmp_path, "series-one")

    assert resolved == PACKAGED_DEFAULT_STORY_PROFILE
