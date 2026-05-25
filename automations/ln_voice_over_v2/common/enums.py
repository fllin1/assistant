"""Shared enums for the LNVO v2 public contracts."""

from __future__ import annotations

from enum import StrEnum


class PipelineStage(StrEnum):
    """Canonical LNVO v2 pipeline stages."""

    PREPARE = "prepare"
    TRANSFORM = "transform"
    DIALOGUE = "dialogue"
    SCENES = "scenes"
    GENERATION = "generation"


class ReviewStatus(StrEnum):
    """Human or agent review state for editable contracts."""

    ACCEPTED = "accepted"
    NEEDS_REVIEW = "needs_review"


class StageStatus(StrEnum):
    """Execution status for orchestration records."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class ArtifactKind(StrEnum):
    """Persisted artifact kinds."""

    PREPARED_VOLUME = "prepared_volume"
    VOLUME_INDEX = "volume_index"
    SEGMENT_FILE = "segment_file"
    DIALOGUE_CHAPTER = "dialogue_chapter"
    SCENES_DRAFT = "scenes_draft"
    SCENES_FINAL = "scenes_final"
    GENERATION_MANIFEST = "generation_manifest"
    AUDIO_MANIFEST = "audio_manifest"
    VISUAL_TIMELINE = "visual_timeline"


class PerspectiveStatus(StrEnum):
    """Whether chapter perspective has been resolved."""

    UNSET = "unset"
    DETECTED = "detected"


class BeatType(StrEnum):
    """Renderable scene beat types."""

    DIALOGUE = "dialogue"
    NARRATION = "narration"
    SILENCE = "silence"
    OMITTED = "omitted"
    CHAPTER_HEADER = "chapter_header"
    NOTE = "note"


class MediaType(StrEnum):
    """Prepared media kinds."""

    IMAGE = "image"
    PAGE_IMAGE = "page_image"
    ILLUSTRATION = "illustration"
