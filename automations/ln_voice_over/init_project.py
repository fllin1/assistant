"""Project initialization for the LN voice-over pipeline.

Creates the folder structure and placeholder config files for a new volume
under `~/.assistant/ln_voice_over/projects/<series>/<volume>/`. The series
directory holds the shared config (characters.json, voices.json); each
volume directory holds the pipeline I/O (source, chapters, ...).
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import SERIES_SUBDIRS, VOLUME_SUBDIRS, series_dir, volume_dir
from .models import Character, CharacterRegistry, VoiceConfig


def slugify(name: str) -> str:
    """Lowercase, replace non-alphanumeric runs with hyphens, strip edges."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


# Legacy flat slugs carried a `-v<N>` suffix that implicitly encoded the
# volume. Accept that form for now and split it into (series, volume).
_LEGACY_VOLUME_SUFFIX = re.compile(r"^(?P<series>.+?)-(?P<volume>v\d+[a-z]?)$")


def split_legacy_slug(slug: str) -> tuple[str, str] | None:
    """Parse a legacy flat slug (`<series>-v<N>`) into `(series, volume)`.

    Returns None when the slug doesn't match the legacy convention.
    Used by the CLI compatibility shim and by resolve_volume() in project.py.
    """
    match = _LEGACY_VOLUME_SUFFIX.match(slug)
    if not match:
        return None
    return match.group("series"), match.group("volume")


def migrate_source_dir(root: Path) -> None:
    """Fold legacy `raw/` and `downloads/` into a single `source/` folder.

    Idempotent: safe to call on already-migrated projects. Empty legacy dirs
    are removed; collisions keep the destination file and leave the source
    in place for manual review.
    """
    source = root / "source"
    for legacy_name in ("raw", "downloads"):
        legacy = root / legacy_name
        if not legacy.exists():
            continue
        source.mkdir(parents=True, exist_ok=True)
        for item in legacy.iterdir():
            dest = source / item.name
            if dest.exists():
                continue
            item.rename(dest)
        if not any(legacy.iterdir()):
            legacy.rmdir()


def _ensure_series_configs(series_root: Path) -> None:
    """Create placeholder characters.json + voices.json at the series level.

    Idempotent: if files already exist they're left alone (even if they
    contain real content from a previous volume's assignment work).
    """
    chars_path = series_root / "config" / "characters.json"
    if not chars_path.exists():
        example = Character(
            name="Example Character",
            aliases=("Example", "Ex"),
            description="Replace with a real character. Delete this entry.",
            gender="female",
            role="main",
        )
        CharacterRegistry(characters=(example,)).save(chars_path)

    voices_path = series_root / "config" / "voices.json"
    if not voices_path.exists():
        VoiceConfig().save(voices_path)


def create_project(series_slug: str, volume_slug: str = "v1") -> Path:
    """Create the series + volume folder structure. Idempotent.

    Args:
        series_slug: Series-level slug (e.g. "classroom-of-the-elite-year-2").
        volume_slug: Volume-level slug (e.g. "v7"). Defaults to "v1" for
            standalone books that don't have a multi-volume structure.

    Returns the volume root directory. Placeholder series configs are created
    on first call; subsequent volumes in the same series reuse them.
    """
    series_root = series_dir(series_slug)
    vol_root = volume_dir(series_slug, volume_slug)

    for subdir in SERIES_SUBDIRS:
        (series_root / subdir).mkdir(parents=True, exist_ok=True)
    for subdir in VOLUME_SUBDIRS:
        (vol_root / subdir).mkdir(parents=True, exist_ok=True)

    # One-time per-volume migrations from the older flat layout
    legacy_attributed = vol_root / "attributed"
    new_resolved = vol_root / "resolved"
    if legacy_attributed.exists() and not any(new_resolved.iterdir()):
        for item in legacy_attributed.iterdir():
            item.rename(new_resolved / item.name)
        legacy_attributed.rmdir()

    migrate_source_dir(vol_root)

    _ensure_series_configs(series_root)

    return vol_root
