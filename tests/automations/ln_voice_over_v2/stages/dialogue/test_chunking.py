"""Tests for dialogue payload chunking and proposal merging."""

from __future__ import annotations

from automations.ln_voice_over_v2.stages.dialogue.agent import (
    CandidateDecision,
    DialogueProposal,
)
from automations.ln_voice_over_v2.stages.dialogue.chunking import (
    attribute_with_chunking,
    merge_proposals,
    split_payload,
)
from automations.ln_voice_over_v2.stages.dialogue.context import (
    ChapterPayload,
    PayloadSegment,
)


def test_split_payload_returns_identity_when_within_cap() -> None:
    """Payloads already within the cap are passed through unchanged."""
    payload = _payload(candidate_count=2)

    chunks = split_payload(payload, max_candidates_per_chunk=2)

    assert chunks == [payload]
    assert chunks[0] is payload


def test_split_payload_partitions_candidates_and_keeps_narration() -> None:
    """Oversized payloads split into ordered, disjoint candidate windows."""
    payload = _payload(candidate_count=5, narrator_hint="Ayanokouji")

    chunks = split_payload(
        payload,
        max_candidates_per_chunk=2,
        context_overlap_segments=1,
    )

    assert [candidate_id for chunk in chunks for candidate_id in chunk.candidate_ids] == list(
        payload.candidate_ids
    )
    assert len({candidate_id for chunk in chunks for candidate_id in chunk.candidate_ids}) == 5
    assert [len(chunk.candidate_ids) for chunk in chunks] == [2, 2, 1]
    assert all(len(chunk.candidate_ids) <= 2 for chunk in chunks)
    assert all(chunk.series == payload.series for chunk in chunks)
    assert all(chunk.volume == payload.volume for chunk in chunks)
    assert all(chunk.chapter_id == payload.chapter_id for chunk in chunks)
    assert all(chunk.narrator_hint == "Ayanokouji" for chunk in chunks)
    assert any(segment.role == "narration" for segment in chunks[0].segments)
    assert any(segment.role == "narration" for segment in chunks[1].segments)


def test_split_payload_tags_lead_in_context_and_excludes_it_from_candidates() -> None:
    """Lead-in overlap is rebuilt as context and never owned by the next chunk."""
    payload = _payload(candidate_count=4)

    chunks = split_payload(
        payload,
        max_candidates_per_chunk=2,
        context_overlap_segments=3,
    )

    assert all(segment.role != "context" for segment in chunks[0].segments)
    assert all(segment.role == "context" for segment in chunks[1].segments[:3])
    assert tuple(segment.segment_id for segment in chunks[1].segments[:3]) == (
        "seg_000002",
        "seg_000003",
        "seg_000004",
    )
    assert tuple(segment.text for segment in chunks[1].segments[:3]) == tuple(
        segment.text for segment in payload.segments[1:4]
    )
    assert chunks[1].candidate_ids == ("seg_000005", "seg_000007")
    assert all(
        segment.segment_id not in chunks[1].candidate_ids for segment in chunks[1].segments[:3]
    )
    assert chunks[1].segments[0] is not payload.segments[1]


def test_split_payload_with_zero_overlap_is_clean_partition() -> None:
    """Disabling overlap leaves no context prefix between chunks."""
    payload = _payload(candidate_count=4)

    chunks = split_payload(
        payload,
        max_candidates_per_chunk=2,
        context_overlap_segments=0,
    )

    assert all(segment.role != "context" for chunk in chunks for segment in chunk.segments)
    assert chunks[0].candidate_ids == ("seg_000001", "seg_000003")
    assert chunks[1].candidate_ids == ("seg_000005", "seg_000007")
    assert tuple(segment.segment_id for chunk in chunks for segment in chunk.segments) == tuple(
        segment.segment_id for segment in payload.segments
    )


def test_split_payload_handles_cap_one_and_exact_multiple() -> None:
    """Cap-one and exact-multiple splits do not create empty chunks."""
    cap_one = split_payload(
        _payload(candidate_count=3),
        max_candidates_per_chunk=1,
        context_overlap_segments=0,
    )
    exact_multiple = split_payload(
        _payload(candidate_count=4),
        max_candidates_per_chunk=2,
        context_overlap_segments=0,
    )

    assert [chunk.candidate_ids for chunk in cap_one] == [
        ("seg_000001",),
        ("seg_000003",),
        ("seg_000005",),
    ]
    assert [chunk.candidate_ids for chunk in exact_multiple] == [
        ("seg_000001", "seg_000003"),
        ("seg_000005", "seg_000007"),
    ]


def test_merge_proposals_unions_identical_duplicates_and_conflicts() -> None:
    """Merge keeps first decisions while surfacing conflicting duplicates."""
    first = proposal(
        narrator_raw="Alice",
        decisions=[
            decision("seg_000001", speaker_raw="Alice"),
            decision("seg_000002", speaker_raw="Bob"),
        ],
        review_notes=("keep", "duplicate-note"),
    )
    second = proposal(
        narrator_raw="Bob",
        decisions=[
            decision("seg_000001", speaker_raw="Alice", reason="same is fine"),
            decision("seg_000002", speaker_raw="Bob", speaker_gender="female"),
            decision("seg_000003", is_dialogue=False, reason="thought"),
        ],
        review_notes=("duplicate-note", "later"),
    )

    merged = merge_proposals([first, second])

    assert [decision.segment_id for decision in merged.decisions] == [
        "seg_000001",
        "seg_000002",
        "seg_000003",
    ]
    assert merged.decisions[1].speaker_raw == "Bob"
    assert merged.review_notes == (
        "keep",
        "duplicate-note",
        "later",
        "conflicting decisions across chunks for seg_000002; kept first",
    )


def test_merge_proposals_picks_narrator_majority_tie_and_all_null() -> None:
    """Narrator merge uses non-null majority and earliest chunk for ties."""
    assert (
        merge_proposals(
            [
                proposal(narrator_raw="Alice"),
                proposal(narrator_raw="Bob"),
                proposal(narrator_raw="Bob"),
            ]
        ).narrator_raw
        == "Bob"
    )
    assert (
        merge_proposals(
            [
                proposal(narrator_raw="Alice"),
                proposal(narrator_raw=None),
                proposal(narrator_raw="Bob"),
            ]
        ).narrator_raw
        == "Alice"
    )
    assert (
        merge_proposals(
            [
                proposal(narrator_raw="Alice"),
                proposal(narrator_raw="Bob"),
                proposal(narrator_raw="Bob"),
                proposal(narrator_raw="Alice"),
            ]
        ).narrator_raw
        == "Alice"
    )
    assert (
        merge_proposals(
            [
                proposal(narrator_raw=None),
                proposal(narrator_raw=None),
            ]
        ).narrator_raw
        is None
    )


def test_attribute_with_chunking_single_chunk_passthrough() -> None:
    """Within-cap payloads call the attribute function once with the original object."""
    payload = _payload(candidate_count=2)
    calls: list[ChapterPayload] = []
    expected = proposal(
        decisions=[
            decision("seg_000001", speaker_raw="Alice"),
            decision("seg_000003", speaker_raw="Bob"),
        ]
    )

    def attribute_chunk(chunk: ChapterPayload) -> DialogueProposal:
        calls.append(chunk)
        return expected

    result = attribute_with_chunking(
        payload,
        attribute_chunk=attribute_chunk,
        max_candidates_per_chunk=2,
    )

    assert result == expected
    assert calls == [payload]
    assert calls[0] is payload


def test_attribute_with_chunking_calls_each_chunk_and_merges() -> None:
    """Oversized payloads are attributed chunk-by-chunk then merged."""
    payload = _payload(candidate_count=5)
    calls: list[ChapterPayload] = []
    canned = [
        proposal(
            narrator_raw="Alice",
            decisions=[
                decision("seg_000001", speaker_raw="Alice"),
                decision("seg_000003", speaker_raw="Bob"),
            ],
            review_notes=("first",),
        ),
        proposal(
            narrator_raw="Bob",
            decisions=[
                decision("seg_000005", speaker_raw="Alice"),
                decision("seg_000007", speaker_raw="Bob"),
            ],
            review_notes=("second",),
        ),
        proposal(
            narrator_raw="Alice",
            decisions=[
                decision("seg_000009", speaker_raw="Alice"),
            ],
            review_notes=("first", "third"),
        ),
    ]

    def attribute_chunk(chunk: ChapterPayload) -> DialogueProposal:
        calls.append(chunk)
        return canned[len(calls) - 1]

    result = attribute_with_chunking(
        payload,
        attribute_chunk=attribute_chunk,
        max_candidates_per_chunk=2,
        context_overlap_segments=1,
    )

    assert [chunk.candidate_ids for chunk in calls] == [
        ("seg_000001", "seg_000003"),
        ("seg_000005", "seg_000007"),
        ("seg_000009",),
    ]
    assert result == merge_proposals(canned)


def _payload(
    *,
    candidate_count: int,
    narrator_hint: str | None = None,
) -> ChapterPayload:
    segments: list[PayloadSegment] = []
    candidate_ids: list[str] = []
    for index in range(candidate_count):
        candidate_id = f"seg_{index * 2 + 1:06d}"
        narration_id = f"seg_{index * 2 + 2:06d}"
        segments.append(
            PayloadSegment(
                segment_id=candidate_id,
                text=f'"Candidate {index + 1}."',
                role="candidate",
            )
        )
        segments.append(
            PayloadSegment(
                segment_id=narration_id,
                text=f"Narration {index + 1}.",
                role="narration",
            )
        )
        candidate_ids.append(candidate_id)

    return ChapterPayload(
        series="series-one",
        volume="v1",
        chapter_id="chapter_01",
        narrator_hint=narrator_hint,
        segments=tuple(segments),
        candidate_ids=tuple(candidate_ids),
    )


def proposal(
    *,
    narrator_raw: str | None = "Alice",
    decisions: list[CandidateDecision] | None = None,
    review_notes: tuple[str, ...] = (),
) -> DialogueProposal:
    return DialogueProposal(
        narrator_raw=narrator_raw,
        decisions=tuple(decisions or ()),
        review_notes=review_notes,
    )


def decision(
    segment_id: str,
    *,
    speaker_raw: str | None = None,
    speaker_gender: str = "unknown",
    is_dialogue: bool = True,
    reason: str = "",
) -> CandidateDecision:
    return CandidateDecision(
        segment_id=segment_id,
        is_dialogue=is_dialogue,
        speaker_raw=speaker_raw,
        speaker_gender=speaker_gender,
        reason=reason,
    )
