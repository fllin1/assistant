"""Interactive pickers for the LN voice-over CLI.

Provides numbered-menu pickers used when the user omits positional args
(e.g. `lnvo split` with no slug) or runs `lnvo` with no subcommand at all.

Kept deliberately small — no persistent state, no caching. Each invocation
is a fresh prompt. If a pipeline stage needs more than a slug, the user
passes flags on the command line as before.
"""

from __future__ import annotations

import typer

from .config import PROJECTS_DIR


def list_project_slugs() -> list[str]:
    """Return existing project slugs, sorted, excluding dotfiles."""
    if not PROJECTS_DIR.exists():
        return []
    return sorted(
        d.name for d in PROJECTS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def pick_slug(prompt: str = "Select a book") -> str:
    """Show a numbered menu of existing projects and return the chosen slug.

    Exits with a helpful message if no projects exist.
    """
    slugs = list_project_slugs()
    if not slugs:
        typer.echo("No projects found. Run `lnvo init` first.")
        raise typer.Exit(1)

    typer.echo(f"\n{prompt}:")
    for i, slug in enumerate(slugs, 1):
        typer.echo(f"  {i}. {slug}")
    typer.echo()

    choice = typer.prompt("Number", type=int, default=1)
    if not 1 <= choice <= len(slugs):
        typer.echo(f"Invalid choice: {choice}")
        raise typer.Exit(1)

    return slugs[choice - 1]


def resolve_slug(book_slug: str | None) -> str:
    """Return `book_slug` if given, otherwise launch the picker.

    Helper used by every command that accepts an optional slug argument.
    """
    return book_slug if book_slug else pick_slug()


# Pipeline stages exposed in the top-level interactive menu. Each entry maps
# a display label to the Typer command name registered in `cli.py`.
STAGES: list[tuple[str, str]] = [
    ("split", "Stage 1: Split volume into chapters"),
    ("clean", "Stage 2: Clean chapter files"),
    ("parse", "Stage 3: Parse cleaned text into segments"),
    ("extract", "Stage 4: Extract speaker attributions"),
    ("resolve", "Stage 4b: Resolve attributions to canonical names"),
    ("review", "Stage 5: Review divergences"),
    ("synthesize", "Stage 6: Synthesize audio"),
    ("show-voices", "Show voice assignments"),
    ("list-books", "List all projects"),
]


def pick_stage() -> str:
    """Show a numbered menu of pipeline stages and return the command name."""
    typer.echo("\nWhat would you like to do?")
    for i, (_, label) in enumerate(STAGES, 1):
        typer.echo(f"  {i:2d}. {label}")
    typer.echo()

    choice = typer.prompt("Number", type=int, default=1)
    if not 1 <= choice <= len(STAGES):
        typer.echo(f"Invalid choice: {choice}")
        raise typer.Exit(1)

    return STAGES[choice - 1][0]


def interactive_menu() -> None:
    """Top-level guided entry point: pick a stage, then a book, then run.

    Invoked when the user runs `lnvo` with no subcommand. Re-dispatches into
    the Typer app with the chosen command + slug. Commands that take no slug
    (list-books) are invoked directly.
    """
    from .cli import app

    stage = pick_stage()

    if stage == "list-books":
        app(["list-books"], standalone_mode=False)
        return

    slug = pick_slug()
    app([stage, slug], standalone_mode=False)
