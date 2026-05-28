"""Stage-local validation for transform artifacts."""

from __future__ import annotations

import logging
import re
from collections import Counter

from ...common.errors import ContractValidationError, ValidationProblem
from .contracts import SegmentFile, VolumeIndex

LOGGER = logging.getLogger("ln_voice_over_v2.transform.validation")
SEGMENT_ID_PATTERN = re.compile(r"^seg_(\d{6})$")


def validate_transform_artifacts(
    index: VolumeIndex,
    segment_files: tuple[SegmentFile, ...],
) -> None:
    """Raise `ContractValidationError` if transform artifact invariants fail.

    Args:
        index: Volume-level index emitted by the transform stage.
        segment_files: Chapter segment artifacts emitted by the transform stage.
    """
    problems: list[ValidationProblem] = []

    chapter_counts = Counter(chapter.chapter_id for chapter in index.chapters)
    for chapter_id, count in sorted(chapter_counts.items()):
        if count > 1:
            problems.append(
                ValidationProblem(
                    code="duplicate_chapter_id",
                    message=f"duplicate chapter_id value: {chapter_id}",
                    path="chapters",
                )
            )

    _validate_orders(
        [chapter.order for chapter in index.chapters],
        duplicate_code="duplicate_order",
        gap_code="nonconsecutive_order",
        path="chapters",
        problems=problems,
    )

    for index_position, chapter in enumerate(index.chapters):
        expected_segments_file = f"segments/{chapter.chapter_id}.json"
        if chapter.segments_file != expected_segments_file:
            problems.append(
                ValidationProblem(
                    code="bad_segments_file",
                    message=(
                        f"segments_file must be {expected_segments_file}: {chapter.segments_file}"
                    ),
                    path=f"chapters[{index_position}].segments_file",
                )
            )
        if not chapter.display_name.strip():
            problems.append(
                ValidationProblem(
                    code="empty_display_name",
                    message="display_name must not be empty",
                    path=f"chapters[{index_position}].display_name",
                )
            )

    for segment_file in segment_files:
        _validate_orders(
            [segment.order for segment in segment_file.segments],
            duplicate_code="duplicate_order",
            gap_code="nonconsecutive_order",
            path=f"segments[{segment_file.chapter_id}]",
            problems=problems,
        )
        for segment_index, segment in enumerate(segment_file.segments):
            segment_path = f"segments[{segment_file.chapter_id}][{segment_index}]"
            match = SEGMENT_ID_PATTERN.match(segment.segment_id)
            if match is None:
                problems.append(
                    ValidationProblem(
                        code="bad_segment_id",
                        message=f"segment_id must match seg_NNNNNN: {segment.segment_id}",
                        path=f"{segment_path}.segment_id",
                    )
                )
            elif int(match.group(1)) != segment_index + 1:
                problems.append(
                    ValidationProblem(
                        code="nonconsecutive_segment_id",
                        message="segment_id suffixes must be contiguous from 1",
                        path=f"{segment_path}.segment_id",
                    )
                )

            if not segment.text.strip():
                problems.append(
                    ValidationProblem(
                        code="empty_segment_text",
                        message="segment text must not be empty",
                        path=f"{segment_path}.text",
                    )
                )

    if problems:
        LOGGER.debug("transform artifact validation failed with %s problems", len(problems))
        raise ContractValidationError(problems)


def _validate_orders(
    orders: list[int],
    *,
    duplicate_code: str,
    gap_code: str,
    path: str,
    problems: list[ValidationProblem],
) -> None:
    counts = Counter(orders)
    for order, count in sorted(counts.items()):
        if count > 1:
            problems.append(
                ValidationProblem(
                    code=duplicate_code,
                    message=f"duplicate order value: {order}",
                    path=path,
                )
            )

    unique_orders = sorted(counts)
    if unique_orders != list(range(len(unique_orders))):
        problems.append(
            ValidationProblem(
                code=gap_code,
                message="order values must be contiguous from 0",
                path=path,
            )
        )
