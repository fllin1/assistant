"""Chunk oversized dialogue attribution payloads and merge chunk proposals."""

from __future__ import annotations

from collections.abc import Callable

from .agent import CandidateDecision, DialogueProposal
from .context import ChapterPayload, PayloadSegment

DEFAULT_MAX_CANDIDATES_PER_CHUNK = 300
DEFAULT_CONTEXT_OVERLAP_SEGMENTS = 8


def split_payload(
    payload: ChapterPayload,
    *,
    max_candidates_per_chunk: int,
    context_overlap_segments: int = DEFAULT_CONTEXT_OVERLAP_SEGMENTS,
) -> list[ChapterPayload]:
    """Split a chapter payload into contiguous candidate-capped chunks."""
    if len(payload.candidate_ids) <= max_candidates_per_chunk:
        return [payload]
    if max_candidates_per_chunk < 1:
        raise ValueError("max_candidates_per_chunk must be at least 1")
    if context_overlap_segments < 0:
        raise ValueError("context_overlap_segments must be non-negative")

    windows: list[tuple[PayloadSegment, ...]] = []
    current_window: list[PayloadSegment] = []
    current_candidate_count = 0
    for segment in payload.segments:
        if segment.role == "candidate" and current_candidate_count >= max_candidates_per_chunk:
            windows.append(tuple(current_window))
            current_window = []
            current_candidate_count = 0

        current_window.append(segment)
        if segment.role == "candidate":
            current_candidate_count += 1

    if current_window:
        windows.append(tuple(current_window))

    chunks: list[ChapterPayload] = []
    previous_window: tuple[PayloadSegment, ...] = ()
    for window in windows:
        context_prefix = _context_prefix(previous_window, context_overlap_segments)
        chunks.append(
            ChapterPayload(
                series=payload.series,
                volume=payload.volume,
                chapter_id=payload.chapter_id,
                narrator_hint=payload.narrator_hint,
                segments=(*context_prefix, *window),
                candidate_ids=tuple(
                    segment.segment_id for segment in window if segment.role == "candidate"
                ),
            )
        )
        previous_window = window
    return chunks


def merge_proposals(proposals: list[DialogueProposal]) -> DialogueProposal:
    """Merge per-chunk dialogue proposals into one chapter-level proposal."""
    decision_by_id: dict[str, CandidateDecision] = {}
    conflict_notes: list[str] = []

    for proposal in proposals:
        for decision in proposal.decisions:
            previous = decision_by_id.get(decision.segment_id)
            if previous is None:
                decision_by_id[decision.segment_id] = decision
                continue

            if (
                previous.is_dialogue != decision.is_dialogue
                or previous.speaker_raw != decision.speaker_raw
                or previous.speaker_gender != decision.speaker_gender
            ):
                conflict_notes.append(
                    f"conflicting decisions across chunks for {decision.segment_id}; kept first"
                )

    notes = [note for proposal in proposals for note in proposal.review_notes]
    notes.extend(conflict_notes)

    return DialogueProposal(
        decisions=tuple(decision_by_id.values()),
        narrator_raw=_majority_narrator(proposals),
        review_notes=tuple(dict.fromkeys(notes)),
    )


def attribute_with_chunking(
    payload: ChapterPayload,
    *,
    attribute_chunk: Callable[[ChapterPayload], DialogueProposal],
    max_candidates_per_chunk: int,
    context_overlap_segments: int = DEFAULT_CONTEXT_OVERLAP_SEGMENTS,
) -> DialogueProposal:
    """Attribute a payload directly or by sequential chunk calls."""
    chunks = split_payload(
        payload,
        max_candidates_per_chunk=max_candidates_per_chunk,
        context_overlap_segments=context_overlap_segments,
    )
    if len(chunks) == 1:
        return attribute_chunk(chunks[0])
    return merge_proposals([attribute_chunk(chunk) for chunk in chunks])


def _context_prefix(
    previous_window: tuple[PayloadSegment, ...],
    context_overlap_segments: int,
) -> tuple[PayloadSegment, ...]:
    """Return rebuilt lead-in context segments for the next chunk."""
    if context_overlap_segments == 0:
        return ()
    return tuple(
        PayloadSegment(
            segment_id=segment.segment_id,
            text=segment.text,
            role="context",
        )
        for segment in previous_window[-context_overlap_segments:]
    )


def _majority_narrator(proposals: list[DialogueProposal]) -> str | None:
    """Return the majority non-null narrator, with earliest chunk as tiebreaker."""
    counts: dict[str, int] = {}
    first_index: dict[str, int] = {}
    for index, proposal in enumerate(proposals):
        narrator = proposal.narrator_raw
        if narrator is None:
            continue
        counts[narrator] = counts.get(narrator, 0) + 1
        first_index.setdefault(narrator, index)

    best: str | None = None
    for narrator, count in counts.items():
        if (
            best is None
            or count > counts[best]
            or (count == counts[best] and first_index[narrator] < first_index[best])
        ):
            best = narrator
    return best
