"""Project initialization for the LN voice-over pipeline.

Creates the folder structure and placeholder config files for a new book
project under ~/.assistant/ln_voice_over/projects/<slug>/.
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import PROJECT_SUBDIRS, project_dir
from .models import Character, CharacterRegistry, VoiceConfig


def slugify(name: str) -> str:
    """Lowercase, replace non-alphanumeric runs with hyphens, strip edges."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


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


def create_project(slug: str) -> Path:
    """Create folder structure and placeholder configs. Idempotent.

    Returns the project root directory.
    """
    root = project_dir(slug)

    # One-time migration: attributed/ → resolved/
    legacy = root / "attributed"
    new = root / "resolved"
    if legacy.exists() and not new.exists():
        legacy.rename(new)

    # Fold raw/ + downloads/ into source/
    migrate_source_dir(root)

    for subdir in PROJECT_SUBDIRS:
        (root / subdir).mkdir(parents=True, exist_ok=True)

    chars_path = root / "config" / "characters.json"
    if not chars_path.exists():
        example = Character(
            name="Example Character",
            aliases=("Example", "Ex"),
            description="Replace with a real character. Delete this entry.",
            gender="female",
            role="main",
        )
        CharacterRegistry(characters=(example,)).save(chars_path)

    voices_path = root / "config" / "voices.json"
    if not voices_path.exists():
        VoiceConfig().save(voices_path)

    return root
