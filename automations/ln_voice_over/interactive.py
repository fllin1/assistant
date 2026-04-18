"""Interactive pickers for the LN voice-over CLI.

Provides numbered-menu pickers used when the user omits positional args
(e.g. `lnvo split` with no slug) or runs `lnvo` with no subcommand at all.

The pickers are two-step: choose a series, then choose a volume. A
"Create new volume in existing series" option appears at each level,
alongside a "Create new series" option.
"""

from __future__ import annotations

import typer

from .project import list_series, list_volumes


def bootstrap_project() -> str:
    """Prompt for series + volume names, create the folders, return `series/volume`.

    Used when the user needs a project and none exist (or they picked the
    "Create new" menu entry). Recommend `/setup-book` for PDF workflows —
    this path is for manual projects (e.g. starting from a .txt volume).
    """
    from .init_project import create_project, slugify

    series_name = typer.prompt("Series name (e.g. 'Mushoku Tensei')")
    series_slug = slugify(series_name)
    volume_name = typer.prompt("Volume slug (e.g. 'v1')", default="v1")
    volume_slug = volume_name.strip() or "v1"

    root = create_project(series_slug, volume_slug)
    typer.echo(f"Created volume: {series_slug}/{volume_slug}")
    typer.echo(f"  {root}")
    typer.echo(f"  Place your .txt volume or PDF in {root / 'source'}/")
    typer.echo("  For a PDF workflow, consider running /setup-book instead.")
    return f"{series_slug}/{volume_slug}"


def add_volume_to(series_slug: str) -> str:
    """Prompt for a new volume slug inside an existing series."""
    from .init_project import create_project

    volume_name = typer.prompt(f"New volume slug in '{series_slug}' (e.g. 'v8')")
    volume_slug = volume_name.strip()
    if not volume_slug:
        typer.echo("Empty volume slug — aborting.")
        raise typer.Exit(1)

    root = create_project(series_slug, volume_slug)
    typer.echo(f"Created volume: {series_slug}/{volume_slug}")
    typer.echo(f"  {root}")
    return f"{series_slug}/{volume_slug}"


def pick_series(prompt: str = "Select a series") -> str:
    """Numbered menu of existing series; creates a new one if none exist."""
    series = list_series()
    if not series:
        typer.echo("No projects found — let's create one.")
        return _create_new_series_pair()

    typer.echo(f"\n{prompt}:")
    for i, slug in enumerate(series, 1):
        typer.echo(f"  {i}. {slug}")
    typer.echo(f"  {len(series) + 1}. Create new series")
    typer.echo()

    choice = typer.prompt("Number", type=int, default=1)
    if choice == len(series) + 1:
        return _create_new_series_pair()
    if not 1 <= choice <= len(series):
        typer.echo(f"Invalid choice: {choice}")
        raise typer.Exit(1)

    return series[choice - 1]


def _create_new_series_pair() -> str:
    """Create a new series + initial volume, returning the `series` slug.

    Used by pick_series when the user picks "Create new series". The
    caller will still run pick_volume(series) afterwards, but since the
    new volume we just made will be the only one, it's the obvious pick.
    """
    pair = bootstrap_project()
    series_slug = pair.split("/")[0]
    return series_slug


def pick_volume(series_slug: str, prompt: str = "Select a volume") -> str:
    """Numbered menu of volumes in a series, or create a new one."""
    volumes = list_volumes(series_slug)
    if not volumes:
        typer.echo(f"No volumes in {series_slug} yet — let's create one.")
        pair = add_volume_to(series_slug)
        return pair.split("/")[1]

    typer.echo(f"\n{prompt} in {series_slug}:")
    for i, vol in enumerate(volumes, 1):
        typer.echo(f"  {i}. {vol}")
    typer.echo(f"  {len(volumes) + 1}. Create new volume in this series")
    typer.echo()

    choice = typer.prompt("Number", type=int, default=1)
    if choice == len(volumes) + 1:
        pair = add_volume_to(series_slug)
        return pair.split("/")[1]
    if not 1 <= choice <= len(volumes):
        typer.echo(f"Invalid choice: {choice}")
        raise typer.Exit(1)

    return volumes[choice - 1]


def pick_book() -> str:
    """Two-step picker returning a canonical `series/volume` string."""
    series_slug = pick_series()
    volume_slug = pick_volume(series_slug)
    return f"{series_slug}/{volume_slug}"


def resolve_book_arg(book: str | None) -> str:
    """Return `book` if given, otherwise launch the two-step picker.

    Helper used by every command that accepts an optional book argument.
    """
    return book if book else pick_book()


# Pipeline stages exposed in the top-level interactive menu. Each entry maps
# a display label to the Typer command name registered in `cli.py`.
STAGES: list[tuple[str, str]] = [
    ("split", "Stage 1: Split volume into chapters"),
    ("clean", "Stage 2: Clean chapter files"),
    ("parse", "Stage 3: Parse cleaned text into segments"),
    ("extract", "Stage 4: Extract speaker attributions"),
    ("resolve", "Stage 5: Resolve attributions to canonical names"),
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
    """Top-level guided entry point: pick a stage, then a book, then run."""
    from .cli import app

    stage = pick_stage()

    if stage == "list-books":
        app(["list-books"], standalone_mode=False)
        return

    book = pick_book()
    app([stage, book], standalone_mode=False)
