"""Cross-file validation for prepared volume artifacts."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ...common.errors import ContractValidationError, ValidationProblem
from .contracts import PreparedVolume


def validate_prepared_volume(volume: PreparedVolume, volume_root: Path) -> None:
    """Raise `ContractValidationError` if filesystem invariants fail.

    Anchor convention: every ArtifactPath in `volume` (text_unit.source_path,
    media.path, media.source_path) is POSIX-relative to `volume_root` — the
    directory that contains both `source/` and `prepared/`. Absolute
    filesystem locations are computed as `volume_root / artifact_path`.
    """
    problems: list[ValidationProblem] = []

    if not volume.text_units:
        problems.append(
            ValidationProblem(
                code="text_units_empty",
                message="prepared volume must contain at least one text unit",
                path="text_units",
            )
        )

    _validate_orders(
        [unit.order for unit in volume.text_units],
        duplicate_code="text_unit_order_duplicate",
        gap_code="text_unit_order_gap",
        path="text_units",
        problems=problems,
    )

    for index, text_unit in enumerate(volume.text_units):
        if not (volume_root / text_unit.source_path).is_file():
            problems.append(
                ValidationProblem(
                    code="text_unit_source_missing",
                    message=f"text unit source path is missing: {text_unit.source_path}",
                    path=f"text_units[{index}].source_path",
                )
            )

    for index, media in enumerate(volume.media):
        if not (volume_root / media.path).is_file():
            problems.append(
                ValidationProblem(
                    code="media_path_missing",
                    message=f"media path is missing: {media.path}",
                    path=f"media[{index}].path",
                )
            )
        if not (volume_root / media.source_path).is_file():
            problems.append(
                ValidationProblem(
                    code="media_source_missing",
                    message=f"media source path is missing: {media.source_path}",
                    path=f"media[{index}].source_path",
                )
            )

    _validate_orders(
        [media.order for media in volume.media],
        duplicate_code="media_order_duplicate",
        gap_code="media_order_gap",
        path="media",
        problems=problems,
    )

    if problems:
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
