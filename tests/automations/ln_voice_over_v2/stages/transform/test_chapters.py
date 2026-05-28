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


def test_prologue_chapter_epilogue_three_chapters(
    default_profile: StoryProfile,
) -> None:
    """Prologue + Chapter 2 + Epilogue yields three chapters with dense order 0/1/2."""
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
        "chapter_01",
        "chapter_02",
        "chapter_03",
    ]


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
                    "subchapters": False,
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
