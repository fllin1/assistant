"""Project initialization for the LN voice-over pipeline.

Creates the folder structure and placeholder config files for a new book
project under ~/.assistant/ln_voice_over/projects/<slug>/.
"""

from __future__ import annotations

import re
from pathlib import Path

import typer

from .config import PROJECT_SUBDIRS, PROJECTS_DIR, project_dir
from .models import Character, CharacterRegistry, VoiceConfig


def slugify(name: str) -> str:
    """Lowercase, replace non-alphanumeric runs with hyphens, strip edges."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def list_projects() -> list[str]:
    """Return sorted slugs of existing projects in PROJECTS_DIR."""
    if not PROJECTS_DIR.exists():
        return []
    return sorted(d.name for d in PROJECTS_DIR.iterdir() if d.is_dir())


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


def interactive_init() -> None:
    """Prompt user to select an existing project or create a new one."""
    projects = list_projects()

    if projects:
        typer.echo("\nExisting projects:")
        for i, name in enumerate(projects, 1):
            typer.echo(f"  {i}. {name}")
        typer.echo(f"  {len(projects) + 1}. Create new project")
        typer.echo()

        choice = typer.prompt(
            "Select a project number",
            type=int,
            default=len(projects) + 1,
        )

        if 1 <= choice <= len(projects):
            slug = projects[choice - 1]
            root = create_project(slug)
            typer.echo(f"\nSelected project: {slug}")
            typer.echo(f"  {root}")
            return

    # Create new project
    name = typer.prompt("Project name (e.g. 'Mushoku Tensei Vol 1')")
    slug = slugify(name)
    typer.echo(f"Slug: {slug}")

    if not typer.confirm("Create this project?", default=True):
        typer.echo("Cancelled.")
        raise typer.Abort()

    root = create_project(slug)
    typer.echo(f"\nCreated project: {slug}")
    typer.echo(f"  {root}")
    for subdir in PROJECT_SUBDIRS:
        typer.echo(f"  {root / subdir}/")
    typer.echo(f"\nNext step: place your .txt volume or PDF in {root / 'source'}/")
