"""Transform-stage orchestration for one prepared LNVO volume."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from ...common import paths
from ...common.ids import ProfileId, SeriesId, VolumeId
from ...common.json_io import load_json_contract, save_json_contract
from ...pipeline.validators import validate_transform_against_prepared
from ..prepare.contracts import PreparedVolume
from . import chapters, segments, validation
from .contracts import VolumeIndex

logger = logging.getLogger("ln_voice_over_v2.transform.runner")


@dataclass(frozen=True)
class TransformConfig:
    """Configuration for a transform-stage run."""

    series: SeriesId
    volume: VolumeId
    data_root: Path = paths.DEFAULT_PROJECT_DATA_ROOT
    story_profile: ProfileId | None = None
    force: bool = False


@dataclass(frozen=True)
class TransformResult:
    """Result metadata from a completed transform-stage run."""

    volume_index_path: Path
    volume_index: VolumeIndex
    segments_dir: Path
    chapter_count: int
    segment_count: int
    needs_review_segment_count: int
    story_profile_source: Path


def run_transform(config: TransformConfig) -> TransformResult:
    """Run the transform stage for one prepared volume.

    Args:
        config: Transform-stage configuration.

    Returns:
        Transform artifact paths, volume index, artifact counts, and the
        resolved story-profile source path.
    """
    prepared_volume_path = paths.prepared_volume_path(
        config.data_root, config.series, config.volume
    )
    prepared = load_json_contract(prepared_volume_path, PreparedVolume)

    story_profile_path = chapters.resolve_story_profile_path(config.data_root, config.series)
    logger.info("transform: using story_profile %s", story_profile_path)
    story_profile = chapters.load_story_profile(story_profile_path)

    splits = chapters.detect_chapters(prepared.text_units, story_profile)
    segment_files = segments.build_segment_files(splits, config.series, config.volume)
    index = VolumeIndex(
        series=config.series,
        volume=config.volume,
        chapters=tuple(split.index_entry for split in splits),
    )

    validation.validate_transform_artifacts(index, segment_files)
    validate_transform_against_prepared(index, segment_files, prepared)

    volume_root = paths.volume_root(config.data_root, config.series, config.volume)
    segments_dir = volume_root / "segments"
    volume_index_path = paths.volume_index_path(config.data_root, config.series, config.volume)
    if config.force:
        shutil.rmtree(segments_dir, ignore_errors=True)
        volume_index_path.unlink(missing_ok=True)

    save_json_contract(volume_index_path, index)
    for segment_file in segment_files:
        save_json_contract(
            paths.segment_file_path(
                config.data_root,
                config.series,
                config.volume,
                segment_file.chapter_id,
            ),
            segment_file,
        )

    segment_count = sum(len(segment_file.segments) for segment_file in segment_files)
    needs_review_segment_count = sum(
        1
        for segment_file in segment_files
        for segment in segment_file.segments
        if segment.parser_hints.get("needs_review") is True
    )

    return TransformResult(
        volume_index_path=volume_index_path,
        volume_index=index,
        segments_dir=segments_dir,
        chapter_count=len(index.chapters),
        segment_count=segment_count,
        needs_review_segment_count=needs_review_segment_count,
        story_profile_source=story_profile_path,
    )
