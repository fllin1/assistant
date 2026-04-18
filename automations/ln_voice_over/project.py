"""Series/volume path resolution and config loaders.

A "project" in the ln_voice_over pipeline is a `<series>/<volume>` pair.
Character registries and voice assignments live at the series level so
that all volumes of the same light novel share one cast. Chapters,
extractions, audio, etc. live at the volume level.

This module is the one place that knows how to turn a CLI argument —
whether `classroom-of-the-elite-year-2/v7` or the legacy
`classroom-of-the-elite-year-2-v7` — into canonical paths, and how to
load the series-level configs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import PROJECTS_DIR, series_dir, volume_dir
from .init_project import split_legacy_slug
from .models import CharacterRegistry, VoiceConfig


@dataclass(frozen=True)
class ResolvedVolume:
    """A resolved `<series>/<volume>` pair and its filesystem paths."""

    series_slug: str
    volume_slug: str
    series_path: Path
    volume_path: Path


def parse_slug(arg: str) -> tuple[str, str]:
    """Split a CLI arg into `(series_slug, volume_slug)`.

    Accepted forms:
      * ``"series/volume"`` — canonical nested form.
      * ``"series-v7"`` — legacy flat slug; the `-v<N>` suffix is peeled off.
      * ``"series"`` — series-only; volume defaults to "v1".
    """
    if "/" in arg:
        parts = arg.strip("/").split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Expected '<series>/<volume>', got: {arg!r}")
        return parts[0], parts[1]

    legacy = split_legacy_slug(arg)
    if legacy:
        return legacy

    return arg, "v1"


def resolve_volume(arg: str) -> ResolvedVolume:
    """Parse a CLI argument into a ResolvedVolume with absolute paths."""
    series_slug, volume_slug = parse_slug(arg)
    return ResolvedVolume(
        series_slug=series_slug,
        volume_slug=volume_slug,
        series_path=series_dir(series_slug),
        volume_path=volume_dir(series_slug, volume_slug),
    )


def load_characters(series_slug: str) -> CharacterRegistry:
    """Load the series-level character registry."""
    path = series_dir(series_slug) / "config" / "characters.json"
    return CharacterRegistry.load(path)


def load_voices(series_slug: str) -> VoiceConfig:
    """Load the series-level voice config."""
    path = series_dir(series_slug) / "config" / "voices.json"
    return VoiceConfig.load(path)


def list_series() -> list[str]:
    """Return all series slugs under PROJECTS_DIR, sorted."""
    if not PROJECTS_DIR.exists():
        return []
    return sorted(
        d.name
        for d in PROJECTS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".") and _looks_like_series(d)
    )


def list_volumes(series_slug: str) -> list[str]:
    """Return volume slugs under a series directory, sorted."""
    root = series_dir(series_slug)
    if not root.exists():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name != "config"
    )


def _looks_like_series(path: Path) -> bool:
    """Return True when `path` is a nested series dir, not a legacy flat project.

    A legacy flat project has pipeline dirs (`chapters/`, `source/`, etc.)
    directly under its root. A series dir has volume subdirs (`v1`, `v7`, ...)
    and/or a series-level `config/` folder. The presence of any pipeline-stage
    directory at the top level is a strong signal that we're looking at an
    un-migrated flat project.
    """
    legacy_markers = {"chapters", "source", "cleaned", "parsed", "extracted", "resolved"}
    names = {c.name for c in path.iterdir() if c.is_dir()}
    if legacy_markers & names:
        return False
    return bool(names)
