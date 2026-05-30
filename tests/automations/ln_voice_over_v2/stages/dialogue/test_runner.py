"""Tests for the dialogue runner."""

from __future__ import annotations

from pathlib import Path

import pytest
from automations.ln_voice_over_v2.common import paths
from automations.ln_voice_over_v2.common.enums import (
    PerspectiveStatus,
    ReviewStatus,
)
from automations.ln_voice_over_v2.common.errors import ContractValidationError
from automations.ln_voice_over_v2.common.json_io import load_json_contract, save_json_contract
from automations.ln_voice_over_v2.series.contracts import Character, CharacterRegistry
from automations.ln_voice_over_v2.stages.dialogue.agent import (
    CandidateDecision,
    DialogueProposal,
)
from automations.ln_voice_over_v2.stages.dialogue.context import ChapterPayload
from automations.ln_voice_over_v2.stages.dialogue.contracts import DialogueChapter
from automations.ln_voice_over_v2.stages.dialogue.runner import (
    DialogueConfig,
    DialogueVolumeConfig,
    run_dialogue,
    run_dialogue_volume,
)
from automations.ln_voice_over_v2.stages.transform.contracts import (
    ChapterIndexEntry,
    Segment,
    SegmentFile,
    VolumeIndex,
)

SERIES = "series-a"
VOLUME = "v01"
CHAPTER = "chapter_01"


def test_valid_dialogue_file_round_trips(tmp_path: Path) -> None:
    write_fixture_tree(tmp_path)

    result = run_dialogue(
        config(tmp_path),
        attribute_fn=lambda _: proposal(
            narrator_raw="Alice",
            decisions=[
                decision("seg_000001", speaker_raw="Alice"),
                decision("seg_000002", speaker_raw="Bob"),
            ],
        ),
    )

    saved = load_json_contract(result.dialogue_path, DialogueChapter)
    assert result.skipped is False
    assert result.accepted_count == 2
    assert result.rejected_count == 0
    assert saved == result.dialogue
    assert saved.status is ReviewStatus.ACCEPTED
    assert saved.review_required is False
    assert [row.speaker for row in saved.dialogues] == ["Alice", "Bob"]
    assert saved.perspective.narrator == "Alice"
    assert saved.perspective.status is PerspectiveStatus.DETECTED


def test_rejected_quote_candidate_records_reason(tmp_path: Path) -> None:
    write_fixture_tree(tmp_path)

    result = run_dialogue(
        config(tmp_path),
        attribute_fn=lambda _: proposal(
            decisions=[
                decision("seg_000001", speaker_raw="Alice"),
                decision("seg_000002", is_dialogue=False, reason="thought"),
            ],
        ),
    )

    assert [(row.segment_id, row.reason) for row in result.dialogue.rejected_candidates] == [
        ("seg_000002", "thought")
    ]


def test_unknown_speaker_requires_review(tmp_path: Path) -> None:
    write_fixture_tree(tmp_path)

    result = run_dialogue(
        config(tmp_path),
        attribute_fn=lambda _: proposal(
            decisions=[
                decision("seg_000001", speaker_raw="Alice"),
                decision("seg_000002", speaker_raw="Mystery"),
            ],
        ),
    )

    assert [row.speaker for row in result.dialogue.dialogues] == ["Alice", "Unknown"]
    assert result.review_required is True
    assert result.dialogue.status is ReviewStatus.NEEDS_REVIEW


def test_alias_normalization(tmp_path: Path) -> None:
    write_fixture_tree(tmp_path)

    result = run_dialogue(
        config(tmp_path),
        attribute_fn=lambda _: proposal(
            narrator_raw="Al",
            decisions=[
                decision("seg_000001", speaker_raw="Al"),
                decision("seg_000002", speaker_raw="Bobby"),
            ],
        ),
    )

    assert result.dialogue.perspective.narrator == "Alice"
    assert [row.speaker for row in result.dialogue.dialogues] == ["Alice", "Bob"]


def test_invalid_segment_reference_fails_before_write(tmp_path: Path) -> None:
    write_fixture_tree(tmp_path, segment_chapter_id="chapter_02")
    dialogue_path = paths.dialogue_chapter_path(tmp_path, SERIES, VOLUME, CHAPTER)

    with pytest.raises(ContractValidationError):
        run_dialogue(
            config(tmp_path),
            attribute_fn=lambda _: proposal(
                decisions=[
                    decision("seg_000001", speaker_raw="Alice"),
                    decision("seg_000002", speaker_raw="Bob"),
                ]
            ),
        )

    assert not dialogue_path.exists()


def test_unresolved_narrator_requires_review(tmp_path: Path) -> None:
    write_fixture_tree(tmp_path)

    result = run_dialogue(
        config(tmp_path),
        attribute_fn=lambda _: proposal(
            narrator_raw=None,
            decisions=[
                decision("seg_000001", speaker_raw="Alice"),
                decision("seg_000002", speaker_raw="Bob"),
            ],
        ),
    )

    assert result.dialogue.perspective.status is PerspectiveStatus.UNSET
    assert result.dialogue.perspective.narrator is None
    assert result.review_required is True
    assert result.dialogue.status is ReviewStatus.NEEDS_REVIEW


def test_unknown_chapter_fails_before_model_call(tmp_path: Path) -> None:
    write_fixture_tree(tmp_path)

    def fail_if_called(_):
        raise AssertionError("attribute_fn should not be called")

    with pytest.raises(ContractValidationError) as exc_info:
        run_dialogue(
            DialogueConfig(
                series=SERIES,
                volume=VOLUME,
                chapter_id="chapter_99",
                data_root=tmp_path,
            ),
            attribute_fn=fail_if_called,
        )

    assert exc_info.value.problems[0].code == "unknown_chapter"


def test_omitted_candidate_is_rejected_and_requires_review(tmp_path: Path) -> None:
    write_fixture_tree(tmp_path)

    result = run_dialogue(
        config(tmp_path),
        attribute_fn=lambda _: proposal(decisions=[decision("seg_000001", speaker_raw="Alice")]),
    )

    assert [(row.segment_id, row.reason) for row in result.dialogue.rejected_candidates] == [
        ("seg_000002", "model_omitted")
    ]
    assert result.review_required is True


def test_skip_existing_preserves_bytes_and_force_regenerates(tmp_path: Path) -> None:
    write_fixture_tree(tmp_path)
    first = run_dialogue(
        config(tmp_path),
        attribute_fn=lambda _: proposal(
            decisions=[
                decision("seg_000001", speaker_raw="Alice"),
                decision("seg_000002", speaker_raw="Bob"),
            ],
        ),
    )
    original_bytes = first.dialogue_path.read_bytes()

    skipped = run_dialogue(
        config(tmp_path),
        attribute_fn=lambda _: proposal(review_notes=("should not run",)),
    )
    assert skipped.skipped is True
    assert first.dialogue_path.read_bytes() == original_bytes

    forced = run_dialogue(
        DialogueConfig(SERIES, VOLUME, CHAPTER, data_root=tmp_path, force=True),
        attribute_fn=lambda _: proposal(
            review_notes=("forced",),
            decisions=[
                decision("seg_000001", speaker_raw="Alice"),
                decision("seg_000002", speaker_raw="Bob"),
            ],
        ),
    )
    assert forced.skipped is False
    assert forced.dialogue.review_notes == ("forced",)
    assert forced.dialogue_path.read_bytes() != original_bytes


def test_resolved_alias_does_not_trigger_unknown_review(tmp_path: Path) -> None:
    write_fixture_tree(tmp_path)

    result = run_dialogue(
        config(tmp_path),
        attribute_fn=lambda _: proposal(
            narrator_raw="Al",
            decisions=[
                decision("seg_000001", speaker_raw="Al"),
                decision("seg_000002", speaker_raw="Bobby"),
            ],
        ),
    )

    assert result.review_required is False
    assert result.dialogue.status is ReviewStatus.ACCEPTED


def test_run_dialogue_threads_timeout_to_codex(tmp_path: Path, monkeypatch) -> None:
    write_fixture_tree(tmp_path)
    captured = {}

    def fake_run_codex_dialogue(prompt: str, *, timeout_seconds: int) -> DialogueProposal:
        captured["timeout_seconds"] = timeout_seconds
        return proposal(
            decisions=[
                decision("seg_000001", speaker_raw="Alice"),
                decision("seg_000002", speaker_raw="Bob"),
            ]
        )

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.runner.run_codex_dialogue",
        fake_run_codex_dialogue,
    )

    run_dialogue(
        DialogueConfig(
            series=SERIES,
            volume=VOLUME,
            chapter_id=CHAPTER,
            data_root=tmp_path,
            timeout_seconds=42,
        ),
    )

    assert captured["timeout_seconds"] == 42


def test_default_dialogue_attribution_chunks_large_payload(tmp_path: Path, monkeypatch) -> None:
    candidate_ids = write_chunking_fixture_tree(tmp_path, candidate_count=5)
    seen_chunks: list[ChapterPayload] = []
    max_candidates_per_chunk = 2

    def fake_run_codex_dialogue(prompt: str, *, timeout_seconds: int) -> DialogueProposal:
        chunk_json = prompt.rsplit("Chapter payload JSON:\n", maxsplit=1)[1]
        chunk = ChapterPayload.model_validate_json(chunk_json)
        seen_chunks.append(chunk)
        return proposal(
            decisions=[
                decision(segment_id, speaker_raw="Alice") for segment_id in chunk.candidate_ids
            ]
        )

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.runner.run_codex_dialogue",
        fake_run_codex_dialogue,
    )

    result = run_dialogue(
        DialogueConfig(
            series=SERIES,
            volume=VOLUME,
            chapter_id=CHAPTER,
            data_root=tmp_path,
            max_candidates_per_chunk=max_candidates_per_chunk,
        ),
    )

    assert [row.segment_id for row in result.dialogue.dialogues] == list(candidate_ids)
    assert result.dialogue.rejected_candidates == ()
    assert not any(
        rejected.reason == "model_omitted" for rejected in result.dialogue.rejected_candidates
    )
    assert (
        len(seen_chunks)
        == (len(candidate_ids) + max_candidates_per_chunk - 1) // max_candidates_per_chunk
    )
    assert [segment_id for chunk in seen_chunks for segment_id in chunk.candidate_ids] == list(
        candidate_ids
    )


def config(tmp_path: Path) -> DialogueConfig:
    return DialogueConfig(
        series=SERIES,
        volume=VOLUME,
        chapter_id=CHAPTER,
        data_root=tmp_path,
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
    is_dialogue: bool = True,
    reason: str = "",
) -> CandidateDecision:
    return CandidateDecision(
        segment_id=segment_id,
        is_dialogue=is_dialogue,
        speaker_raw=speaker_raw,
        reason=reason,
    )


def write_fixture_tree(
    tmp_path: Path,
    *,
    segment_chapter_id: str = CHAPTER,
) -> None:
    volume_index_path = paths.volume_index_path(tmp_path, SERIES, VOLUME)
    segment_path = paths.segment_file_path(tmp_path, SERIES, VOLUME, CHAPTER)
    characters_path = paths.characters_config_path(tmp_path, SERIES)

    save_json_contract(
        volume_index_path,
        VolumeIndex(
            series=SERIES,
            volume=VOLUME,
            chapters=(
                ChapterIndexEntry(
                    chapter_id=CHAPTER,
                    order=0,
                    segments_file=f"segments/{CHAPTER}.json",
                    display_name="Chapter 1",
                ),
            ),
        ),
    )
    save_json_contract(
        segment_path,
        SegmentFile(
            series=SERIES,
            volume=VOLUME,
            chapter_id=segment_chapter_id,
            segments=(
                Segment(
                    segment_id="seg_000001",
                    order=0,
                    text='"Hello," Alice said.',
                    parser_hints={"quote_candidate": True},
                ),
                Segment(
                    segment_id="seg_000002",
                    order=1,
                    text='"Hi," Bob said.',
                    parser_hints={"quote_candidate": True},
                ),
            ),
        ),
    )
    save_json_contract(
        characters_path,
        CharacterRegistry(
            characters=(
                Character(name="Alice", aliases=("Al",)),
                Character(name="Bob", aliases=("Bobby",)),
            ),
        ),
    )


def write_chunking_fixture_tree(tmp_path: Path, *, candidate_count: int) -> tuple[str, ...]:
    candidate_ids = tuple(f"seg_{index + 1:06d}" for index in range(candidate_count))

    save_json_contract(
        paths.volume_index_path(tmp_path, SERIES, VOLUME),
        VolumeIndex(
            series=SERIES,
            volume=VOLUME,
            chapters=(
                ChapterIndexEntry(
                    chapter_id=CHAPTER,
                    order=0,
                    segments_file=f"segments/{CHAPTER}.json",
                    display_name="Chunked Chapter",
                ),
            ),
        ),
    )
    save_json_contract(
        paths.segment_file_path(tmp_path, SERIES, VOLUME, CHAPTER),
        SegmentFile(
            series=SERIES,
            volume=VOLUME,
            chapter_id=CHAPTER,
            segments=tuple(
                Segment(
                    segment_id=segment_id,
                    order=index,
                    text=f'"Line {index + 1}," Alice said.',
                    parser_hints={"quote_candidate": True},
                )
                for index, segment_id in enumerate(candidate_ids)
            ),
        ),
    )
    save_json_contract(
        paths.characters_config_path(tmp_path, SERIES),
        CharacterRegistry(
            characters=(
                Character(name="Alice", aliases=("Al",)),
                Character(name="Bob", aliases=("Bobby",)),
            ),
        ),
    )
    return candidate_ids


CHAPTER_TWO = "chapter_02"


def _accept_both(_payload: object) -> DialogueProposal:
    return proposal(
        decisions=[
            decision("seg_000001", speaker_raw="Alice"),
            decision("seg_000002", speaker_raw="Bob"),
        ]
    )


def write_multi_chapter_tree(tmp_path: Path) -> None:
    save_json_contract(
        paths.volume_index_path(tmp_path, SERIES, VOLUME),
        VolumeIndex(
            series=SERIES,
            volume=VOLUME,
            chapters=(
                ChapterIndexEntry(
                    chapter_id=CHAPTER,
                    order=0,
                    segments_file=f"segments/{CHAPTER}.json",
                    display_name="Chapter 1",
                ),
                ChapterIndexEntry(
                    chapter_id=CHAPTER_TWO,
                    order=1,
                    segments_file=f"segments/{CHAPTER_TWO}.json",
                    display_name="Chapter 2",
                ),
            ),
        ),
    )
    for chapter_id in (CHAPTER, CHAPTER_TWO):
        save_json_contract(
            paths.segment_file_path(tmp_path, SERIES, VOLUME, chapter_id),
            SegmentFile(
                series=SERIES,
                volume=VOLUME,
                chapter_id=chapter_id,
                segments=(
                    Segment(
                        segment_id="seg_000001",
                        order=0,
                        text='"Hello," Alice said.',
                        parser_hints={"quote_candidate": True},
                    ),
                    Segment(
                        segment_id="seg_000002",
                        order=1,
                        text='"Hi," Bob said.',
                        parser_hints={"quote_candidate": True},
                    ),
                ),
            ),
        )
    save_json_contract(
        paths.characters_config_path(tmp_path, SERIES),
        CharacterRegistry(
            characters=(
                Character(name="Alice", aliases=("Al",)),
                Character(name="Bob", aliases=("Bobby",)),
            ),
        ),
    )


def test_run_dialogue_volume_processes_all_chapters(tmp_path: Path) -> None:
    write_multi_chapter_tree(tmp_path)

    result = run_dialogue_volume(
        DialogueVolumeConfig(series=SERIES, volume=VOLUME, data_root=tmp_path, workers=2),
        attribute_fn=_accept_both,
    )

    assert [outcome.chapter_id for outcome in result.outcomes] == [CHAPTER, CHAPTER_TWO]
    assert result.written == 2
    assert result.skipped == 0
    assert result.failed == 0
    assert paths.dialogue_chapter_path(tmp_path, SERIES, VOLUME, CHAPTER).exists()
    assert paths.dialogue_chapter_path(tmp_path, SERIES, VOLUME, CHAPTER_TWO).exists()


def test_run_dialogue_volume_skips_existing_unless_force(tmp_path: Path) -> None:
    write_multi_chapter_tree(tmp_path)

    first = run_dialogue_volume(
        DialogueVolumeConfig(series=SERIES, volume=VOLUME, data_root=tmp_path),
        attribute_fn=_accept_both,
    )
    assert first.written == 2

    again = run_dialogue_volume(
        DialogueVolumeConfig(series=SERIES, volume=VOLUME, data_root=tmp_path),
        attribute_fn=_accept_both,
    )
    assert again.skipped == 2
    assert again.written == 0

    forced = run_dialogue_volume(
        DialogueVolumeConfig(series=SERIES, volume=VOLUME, data_root=tmp_path, force=True),
        attribute_fn=_accept_both,
    )
    assert forced.written == 2
    assert forced.skipped == 0


def test_run_dialogue_volume_isolates_per_chapter_failure(tmp_path: Path) -> None:
    write_multi_chapter_tree(tmp_path)

    def attribute(payload: object) -> DialogueProposal:
        if getattr(payload, "chapter_id", None) == CHAPTER_TWO:
            raise RuntimeError("boom")
        return _accept_both(payload)

    result = run_dialogue_volume(
        DialogueVolumeConfig(series=SERIES, volume=VOLUME, data_root=tmp_path, workers=2),
        attribute_fn=attribute,
    )

    by_id = {outcome.chapter_id: outcome for outcome in result.outcomes}
    assert by_id[CHAPTER].error is None
    assert by_id[CHAPTER].result is not None
    assert by_id[CHAPTER_TWO].result is None
    assert by_id[CHAPTER_TWO].error is not None
    assert "boom" in by_id[CHAPTER_TWO].error
    assert result.written == 1
    assert result.failed == 1


def test_run_dialogue_volume_threads_timeout_to_codex(tmp_path: Path, monkeypatch) -> None:
    write_multi_chapter_tree(tmp_path)
    seen = []

    def fake_run_codex_dialogue(prompt: str, *, timeout_seconds: int) -> DialogueProposal:
        seen.append(timeout_seconds)
        return _accept_both(None)

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.runner.run_codex_dialogue",
        fake_run_codex_dialogue,
    )

    run_dialogue_volume(
        DialogueVolumeConfig(
            series=SERIES,
            volume=VOLUME,
            data_root=tmp_path,
            workers=2,
            timeout_seconds=99,
        ),
    )

    assert len(seen) == 2
    assert all(value == 99 for value in seen)
