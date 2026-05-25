"""Runtime artifact path conventions for LNVO v2."""

from __future__ import annotations

from pathlib import Path

from .enums import ArtifactKind
from .ids import ChapterId, SeriesId, VolumeId

DEFAULT_PROJECT_DATA_ROOT = Path.home() / ".assistant" / "ln_voice_over_v2" / "projects"


def series_root(data_root: Path, series: SeriesId) -> Path:
    """Return the runtime series root."""
    return data_root / series


def volume_root(data_root: Path, series: SeriesId, volume: VolumeId) -> Path:
    """Return the runtime volume root."""
    return series_root(data_root, series) / volume


def prepared_volume_path(data_root: Path, series: SeriesId, volume: VolumeId) -> Path:
    """Return the prepared volume artifact path."""
    return volume_root(data_root, series, volume) / "prepared" / "volume.json"


def volume_index_path(data_root: Path, series: SeriesId, volume: VolumeId) -> Path:
    """Return the transform volume index path."""
    return volume_root(data_root, series, volume) / "volume_index.json"


def segment_file_path(
    data_root: Path, series: SeriesId, volume: VolumeId, chapter_id: ChapterId
) -> Path:
    """Return a chapter segment artifact path."""
    return volume_root(data_root, series, volume) / "segments" / f"{chapter_id}.json"


def dialogue_chapter_path(
    data_root: Path, series: SeriesId, volume: VolumeId, chapter_id: ChapterId
) -> Path:
    """Return a dialogue chapter artifact path."""
    return volume_root(data_root, series, volume) / "dialogue" / f"{chapter_id}.json"


def scene_document_path(
    data_root: Path,
    series: SeriesId,
    volume: VolumeId,
    chapter_id: ChapterId,
    artifact_kind: ArtifactKind,
) -> Path:
    """Return a draft or final scenes artifact path."""
    if artifact_kind == ArtifactKind.SCENES_DRAFT:
        folder = "draft"
    elif artifact_kind == ArtifactKind.SCENES_FINAL:
        folder = "final"
    else:
        raise ValueError("scene document kind must be scenes_draft or scenes_final")
    return volume_root(data_root, series, volume) / "scenes" / folder / f"{chapter_id}.json"


def generation_dir(
    data_root: Path, series: SeriesId, volume: VolumeId, chapter_id: ChapterId
) -> Path:
    """Return a chapter generation package directory."""
    return volume_root(data_root, series, volume) / "generation" / chapter_id
