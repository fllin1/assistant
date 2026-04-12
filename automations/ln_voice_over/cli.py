"""CLI interface for the LN voice-over pipeline.

Typer app with one command per pipeline stage plus a run-all command.
Each command reads from the appropriate project subdirectory and writes
to its own output directory.

Usage:
    python -m automations.ln_voice_over.cli split <book-slug>
    python -m automations.ln_voice_over.cli clean <book-slug>
    python -m automations.ln_voice_over.cli parse <book-slug>
    python -m automations.ln_voice_over.cli attribute <book-slug> [--chapter N]
    python -m automations.ln_voice_over.cli review <book-slug> [--chapter N]
    python -m automations.ln_voice_over.cli synthesize <book-slug> [--chapter N]
    python -m automations.ln_voice_over.cli run-all <book-slug> [--from-stage STAGE]
"""

from __future__ import annotations

import typer

from .config import PROJECTS_DIR

app = typer.Typer(
    name="lnvo",
    help="Light novel text-to-audiobook pipeline.",
)


@app.command()
def init() -> None:
    """Initialize or select a project."""
    from .init_project import interactive_init

    interactive_init()


@app.command()
def list_books() -> None:
    """
    Lists all book slug names in the ~/.assistant/ln_voice_over/ dir.
    """
    for project in PROJECTS_DIR.iterdir():
        if not project.name.startswith("."):
            typer.echo(project.name)


@app.command()
def split(book_slug: str) -> None:
    """Stage 1: Split a volume .txt into chapter files.

    Expects the volume file at:
        ~/.assistant/ln_voice_over/projects/<book-slug>/raw/

    Outputs chapter files and manifest.json to:
        ~/.assistant/ln_voice_over/projects/<book-slug>/chapters/
    """
    from .split import split_volume, write_manifest

    root = PROJECTS_DIR / book_slug
    raw_dir = root / "raw"
    output_dir = root / "chapters"

    txt_files = sorted(raw_dir.glob("*.txt"))
    if not txt_files:
        typer.echo(f"No .txt files found in {raw_dir}")
        raise typer.Exit(1)

    # Split the first .txt file found
    source = txt_files[0]
    if len(txt_files) > 1:
        typer.echo(f"Multiple .txt files found, using: {source.name}")

    chapters = split_volume(source, output_dir)
    write_manifest(chapters, output_dir)
    typer.echo(f"Split into {len(chapters)} chapter(s) → {output_dir}")


@app.command()
def clean(book_slug: str) -> None:
    """Stage 2: Clean chapter files (remove watermarks, page numbers).

    Reads from chapters/, writes to cleaned/.
    """
    from .clean import clean_all

    root = PROJECTS_DIR / book_slug
    chapters_dir = root / "chapters"
    output_dir = root / "cleaned"

    txt_files = sorted(chapters_dir.glob("*.txt"))
    if not txt_files:
        typer.echo(f"No chapter files found in {chapters_dir}")
        raise typer.Exit(1)

    results = clean_all(chapters_dir, output_dir)
    typer.echo(f"Cleaned {len(results)} chapter(s) → {output_dir}")


@app.command()
def parse(book_slug: str) -> None:
    """Stage 3: Parse cleaned text into typed segments.

    Reads from cleaned/ + chapters/manifest.json, writes JSON to parsed/.
    """
    ...


@app.command()
def attribute(
    book_slug: str,
    chapter: int | None = typer.Option(None, help="Process only this chapter number."),
) -> None:
    """Stage 4: Attribute dialogue speakers via LLM.

    Reads from parsed/ + config/characters.json, writes to attributed/.
    """
    ...


@app.command()
def review(
    book_slug: str,
    chapter: int | None = typer.Option(None, help="Review only this chapter."),
    only_low_confidence: bool = typer.Option(False, help="Show only flagged segments."),
    approve_all: bool = typer.Option(False, help="Approve all without review."),
) -> None:
    """Stage 5: Review and correct speaker attributions.

    Reads from attributed/, writes to reviewed/.
    """
    ...


@app.command()
def synthesize(
    book_slug: str,
    chapter: int | None = typer.Option(None, help="Synthesize only this chapter."),
) -> None:
    """Stage 6: Synthesize audio and assemble chapter files.

    Reads from reviewed/ + config/voices.json, writes to audio/.
    """
    ...


@app.command(name="run-all")
def run_all(
    book_slug: str,
    from_stage: str = typer.Option("split", help="Stage to start from."),
) -> None:
    """Run the full pipeline (or resume from a stage).

    Stages: split, clean, parse, attribute, review, synthesize.
    """
    ...


if __name__ == "__main__":
    app()
