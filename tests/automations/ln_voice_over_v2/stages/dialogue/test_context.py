"""Context payload tests for the dialogue stage."""

from __future__ import annotations

from automations.ln_voice_over_v2.series.contracts import StoryProfile
from automations.ln_voice_over_v2.stages.dialogue.context import (
    build_chapter_payload,
    select_candidates,
)
from automations.ln_voice_over_v2.stages.transform.contracts import Segment, SegmentFile


def test_select_candidates_picks_only_quote_candidates() -> None:
    """Candidate selection honors only explicit `quote_candidate is True` hints."""
    segment_file = _segment_file()

    candidates = select_candidates(segment_file)

    assert [segment.segment_id for segment in candidates] == ["seg_000002", "seg_000004"]


def test_build_chapter_payload_tags_roles_and_preserves_text() -> None:
    """The chapter payload preserves text and records candidate ids in order."""
    segment_file = _segment_file()
    story_profile = StoryProfile(
        profile_id="default",
        display_name="Default",
        rules={"default_narrator": "Ayanokouji Kiyotaka"},
    )

    payload = build_chapter_payload(segment_file, story_profile)

    assert payload.series == "series-one"
    assert payload.volume == "v1"
    assert payload.chapter_id == "chapter_01"
    assert payload.narrator_hint == "Ayanokouji Kiyotaka"
    assert payload.candidate_ids == ("seg_000002", "seg_000004")
    assert [segment.role for segment in payload.segments] == [
        "narration",
        "candidate",
        "narration",
        "candidate",
    ]
    assert [segment.text for segment in payload.segments] == [
        "The hallway was quiet.",
        '"What are you planning?"',
        "I did not answer.",
        '"Nothing."',
    ]


def _segment_file() -> SegmentFile:
    return SegmentFile(
        series="series-one",
        volume="v1",
        chapter_id="chapter_01",
        segments=(
            Segment(segment_id="seg_000001", order=0, text="The hallway was quiet."),
            Segment(
                segment_id="seg_000002",
                order=1,
                text='"What are you planning?"',
                parser_hints={"quote_candidate": True},
            ),
            Segment(
                segment_id="seg_000003",
                order=2,
                text="I did not answer.",
                parser_hints={"quote_candidate": False},
            ),
            Segment(
                segment_id="seg_000004",
                order=3,
                text='"Nothing."',
                parser_hints={"quote_candidate": True},
            ),
        ),
    )
