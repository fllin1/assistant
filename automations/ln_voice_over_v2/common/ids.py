"""Canonical identifiers and artifact-relative path validation."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, StringConstraints

type SlugId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]
type SeriesId = SlugId
type VolumeId = SlugId
type ProfileId = SlugId
type AssetId = SlugId
type ChapterId = Annotated[str, StringConstraints(pattern=r"^chapter_[0-9]{2}(_[0-9]+)?$")]
type TextUnitId = Annotated[str, StringConstraints(pattern=r"^unit_[0-9]{6}$")]
type SegmentId = Annotated[str, StringConstraints(pattern=r"^seg_[0-9]{6}$")]
type SceneId = Annotated[str, StringConstraints(pattern=r"^scene_[0-9]{4}$")]
type BeatId = Annotated[str, StringConstraints(pattern=r"^beat_[0-9]{4}$")]


def validate_artifact_path(value: str) -> str:
    """Validate a POSIX-style artifact-relative path."""
    if not value:
        raise ValueError("artifact path cannot be empty")
    if value.startswith("/"):
        raise ValueError("artifact path must be relative")
    if "\\" in value:
        raise ValueError("artifact path must use POSIX separators")

    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("artifact path cannot contain empty, '.', or '..' parts")
    return value


type ArtifactPath = Annotated[str, AfterValidator(validate_artifact_path)]
