"""Tests for REVIEW-boundary construction and canonical Speaker validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from automations.ln_voice_over.models import (
    Chapter,
    Character,
    CharacterRegistry,
    NarratorStatus,
    Segment,
    SegmentType,
)
from automations.ln_voice_over.review import (
    ReviewValidationError,
    build_reviewed_chapter,
    validate_reviewed_chapter,
)
from automations.ln_voice_over.scripts import apply_corrections


@pytest.fixture
def registry() -> CharacterRegistry:
    return CharacterRegistry(
        characters=(
            Character(name="Ayanokouji Kiyotaka", aliases=("Ayanokouji",)),
            Character(name="Horikita Suzune", aliases=("Horikita",)),
            Character(name="Kushida Kikyou", aliases=("Kushida",)),
        )
    )


def make_chapter(
    *segments: Segment,
    narrator_status: NarratorStatus = NarratorStatus.DETECTED,
    narrator: str | None = "Ayanokouji",
) -> Chapter:
    return Chapter(
        chapter_number=1,
        title="Test",
        source_file="chapter_01.txt",
        narrator_status=narrator_status,
        narrator=narrator,
        segments=segments,
    )


def segment(index: int, segment_type: SegmentType, text: str = "text") -> Segment:
    return Segment(index=index, segment_type=segment_type, text=text)


def write_manifest(project_dir: Path, narrator: str | None = "Ayanokouji") -> None:
    manifest_path = project_dir / "chapters" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "number": 1,
                    "title": "Test",
                    "file": "chapter_01.txt",
                    "narrator_status": "detected",
                    "narrator": narrator,
                }
            ]
        ),
        encoding="utf-8",
    )


def test_reviewed_builder_sets_structural_speakers(registry: CharacterRegistry):
    chapter = make_chapter(
        segment(0, SegmentType.CHAPTER_HEADER, "Chapter 1: Test"),
        segment(1, SegmentType.NARRATION, "He walked in."),
        segment(2, SegmentType.SCENE_BREAK, "***"),
        segment(3, SegmentType.DIALOGUE, '"Hello."'),
    )

    reviewed, changes = build_reviewed_chapter(chapter, {"3": "Horikita"}, [], registry)

    assert reviewed.reviewed is True
    assert changes == []
    assert [s.speaker for s in reviewed.segments] == [
        "Narrator",
        "Narrator",
        None,
        "Horikita Suzune",
    ]
    assert reviewed.narrator == "Ayanokouji Kiyotaka"


def test_dialogue_accepts_reserved_speakers(registry: CharacterRegistry):
    chapter = make_chapter(
        segment(0, SegmentType.DIALOGUE, '"Unknown speaker."'),
        segment(1, SegmentType.DIALOGUE, '"inner phrase"'),
    )

    reviewed, _changes = build_reviewed_chapter(
        chapter,
        {"0": "Unknown", "1": "Narrator"},
        [],
        registry,
    )

    assert [s.speaker for s in reviewed.segments] == ["Unknown", "Narrator"]


def test_correction_overrides_and_is_canonicalised(registry: CharacterRegistry):
    chapter = make_chapter(segment(0, SegmentType.DIALOGUE, '"Hello."'))

    reviewed, changes = build_reviewed_chapter(
        chapter,
        {"0": "Horikita"},
        [{"index": 0, "speaker": "Kushida"}],
        registry,
    )

    assert reviewed.segments[0].speaker == "Kushida Kikyou"
    assert changes == [
        {
            "index": 0,
            "old": "Horikita Suzune",
            "new": "Kushida Kikyou",
        }
    ]


def test_noop_correction_is_not_reported(registry: CharacterRegistry):
    chapter = make_chapter(segment(0, SegmentType.DIALOGUE, '"Hello."'))

    reviewed, changes = build_reviewed_chapter(
        chapter,
        {"0": "Horikita"},
        [{"index": 0, "speaker": "Horikita Suzune"}],
        registry,
    )

    assert reviewed.segments[0].speaker == "Horikita Suzune"
    assert changes == []


def test_missing_dialogue_attribution_fails(registry: CharacterRegistry):
    chapter = make_chapter(segment(0, SegmentType.DIALOGUE, '"Hello."'))

    with pytest.raises(ReviewValidationError, match="missing a speaker"):
        build_reviewed_chapter(chapter, {}, [], registry)


def test_unresolved_speaker_fails_as_registry_gap(registry: CharacterRegistry):
    chapter = make_chapter(segment(0, SegmentType.DIALOGUE, '"Hello."'))

    with pytest.raises(ReviewValidationError, match="Registry gap"):
        build_reviewed_chapter(chapter, {"0": "Mystery Person"}, [], registry)


def test_unresolved_narrator_fails_as_registry_gap(registry: CharacterRegistry):
    chapter = make_chapter(
        segment(0, SegmentType.NARRATION, "He entered."),
        narrator="Mystery Person",
    )

    with pytest.raises(ReviewValidationError, match=r"chapter narrator.*Registry gap"):
        build_reviewed_chapter(chapter, {}, [], registry)


def test_review_canonicalises_narrator_alias(registry: CharacterRegistry):
    chapter = make_chapter(
        segment(0, SegmentType.NARRATION, "He entered."),
        narrator="Horikita",
    )

    reviewed, _changes = build_reviewed_chapter(chapter, {}, [], registry)

    assert reviewed.narrator == "Horikita Suzune"


def test_review_requires_narrator_detection(registry: CharacterRegistry):
    chapter = make_chapter(
        segment(0, SegmentType.NARRATION, "He entered."),
        narrator_status=NarratorStatus.UNSET,
        narrator=None,
    )

    with pytest.raises(ReviewValidationError, match="narrator detection has not run"):
        build_reviewed_chapter(chapter, {}, [], registry)


def test_validation_rejects_non_canonical_registry_alias(registry: CharacterRegistry):
    chapter = make_chapter(
        segment(0, SegmentType.DIALOGUE, '"Hello."').model_copy(update={"speaker": "Horikita"})
    )

    with pytest.raises(ReviewValidationError, match="must use canonical speaker"):
        validate_reviewed_chapter(chapter, registry)


def test_i_normalises_through_narrator(registry: CharacterRegistry):
    chapter = make_chapter(segment(0, SegmentType.DIALOGUE, '"I said hello."'))

    reviewed, _changes = build_reviewed_chapter(chapter, {"0": "I"}, [], registry)

    assert reviewed.segments[0].speaker == "Ayanokouji Kiyotaka"


def test_i_without_narrator_fails(registry: CharacterRegistry):
    chapter = make_chapter(segment(0, SegmentType.DIALOGUE, '"I said hello."'), narrator=None)

    with pytest.raises(ReviewValidationError, match="unresolved speaker"):
        build_reviewed_chapter(chapter, {"0": "I"}, [], registry)


def test_apply_corrections_writes_reviewed_chapter_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: CharacterRegistry,
):
    parsed = make_chapter(
        segment(0, SegmentType.NARRATION, "He entered."),
        segment(1, SegmentType.DIALOGUE, '"Hello."'),
    )
    project_dir = tmp_path / "series" / "v1"
    parsed_path = project_dir / "parsed" / "chapter_01.json"
    original_path = project_dir / "extracted" / "chapter_01" / "claude-sonnet_skill_20260101.json"
    parsed.save(parsed_path)
    write_manifest(project_dir)
    original_path.parent.mkdir(parents=True)
    original_path.write_text(json.dumps({"1": "Horikita"}), encoding="utf-8")

    monkeypatch.setattr(apply_corrections, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(apply_corrections, "load_characters", lambda _series_slug: registry)
    monkeypatch.setattr(
        sys,
        "argv",
        ["apply_corrections.py", "series/v1", "1", '[{"index": 1, "speaker": "Kushida"}]'],
    )

    apply_corrections.main()

    reviewed = Chapter.load(project_dir / "reviewed" / "chapter_01.json")
    report = json.loads(
        (project_dir / "reviewed" / "chapter_01_report.json").read_text(encoding="utf-8")
    )
    assert [s.speaker for s in reviewed.segments] == ["Narrator", "Kushida Kikyou"]
    assert report["total_segments"] == 2
    assert report["total_corrections"] == 1
    assert report["changes"] == [{"index": 1, "old": "Horikita Suzune", "new": "Kushida Kikyou"}]


def test_apply_corrections_refreshes_narrator_from_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: CharacterRegistry,
):
    parsed = make_chapter(
        segment(0, SegmentType.DIALOGUE, '"I said hello."'),
        narrator_status=NarratorStatus.UNSET,
        narrator=None,
    )
    project_dir = tmp_path / "series" / "v1"
    parsed_path = project_dir / "parsed" / "chapter_01.json"
    original_path = project_dir / "extracted" / "chapter_01" / "claude-sonnet_skill_20260101.json"
    parsed.save(parsed_path)
    write_manifest(project_dir)
    original_path.parent.mkdir(parents=True)
    original_path.write_text(json.dumps({"0": "I"}), encoding="utf-8")

    monkeypatch.setattr(apply_corrections, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(apply_corrections, "load_characters", lambda _series_slug: registry)
    monkeypatch.setattr(sys, "argv", ["apply_corrections.py", "series/v1", "1", "[]"])

    apply_corrections.main()

    reviewed = Chapter.load(project_dir / "reviewed" / "chapter_01.json")
    assert reviewed.narrator_status == NarratorStatus.DETECTED
    assert reviewed.narrator == "Ayanokouji Kiyotaka"
    assert reviewed.segments[0].speaker == "Ayanokouji Kiyotaka"


def test_apply_corrections_does_not_write_outputs_when_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: CharacterRegistry,
):
    parsed = make_chapter(segment(0, SegmentType.DIALOGUE, '"Hello."'))
    project_dir = tmp_path / "series" / "v1"
    parsed_path = project_dir / "parsed" / "chapter_01.json"
    original_path = project_dir / "extracted" / "chapter_01" / "claude-sonnet_skill_20260101.json"
    reviewed_path = project_dir / "reviewed" / "chapter_01.json"
    report_path = project_dir / "reviewed" / "chapter_01_report.json"
    parsed.save(parsed_path)
    write_manifest(project_dir)
    original_path.parent.mkdir(parents=True)
    original_path.write_text(json.dumps({"0": "Mystery Person"}), encoding="utf-8")
    reviewed_path.parent.mkdir(parents=True)
    reviewed_path.write_text("existing reviewed", encoding="utf-8")
    report_path.write_text("existing report", encoding="utf-8")

    monkeypatch.setattr(apply_corrections, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(apply_corrections, "load_characters", lambda _series_slug: registry)
    monkeypatch.setattr(sys, "argv", ["apply_corrections.py", "series/v1", "1", "[]"])

    with pytest.raises(SystemExit) as exc:
        apply_corrections.main()

    assert exc.value.code == 1
    assert reviewed_path.read_text(encoding="utf-8") == "existing reviewed"
    assert report_path.read_text(encoding="utf-8") == "existing report"
