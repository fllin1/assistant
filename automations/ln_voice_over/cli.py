"""CLI interface for the LN voice-over pipeline.

Typer app with one command per pipeline stage plus a run-all command.
Each command reads from the appropriate project subdirectory and writes
to its own output directory.

Usage:
    python -m automations.ln_voice_over.cli split <book-slug>
    python -m automations.ln_voice_over.cli clean <book-slug>
    python -m automations.ln_voice_over.cli parse <book-slug>
    python -m automations.ln_voice_over.cli attribute <book-slug> [--chapter N]
    python -m automations.ln_voice_over.cli review <book-slug> [--chapter N] [--only-low-confidence] [--approve-all]
    python -m automations.ln_voice_over.cli synthesize <book-slug> [--chapter N]
    python -m automations.ln_voice_over.cli run-all <book-slug> [--from-stage STAGE]
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="lnvo",
    help="Light novel text-to-audiobook pipeline.",
)


@app.command()
def split(book_slug: str) -> None:
    """Stage 1: Split a volume .txt into chapter files.

    Expects the volume file at:
        ~/.assistant/ln_voice_over/projects/<book-slug>/raw/

    Outputs chapter files and manifest.json to:
        ~/.assistant/ln_voice_over/projects/<book-slug>/chapters/
    """
    ...


@app.command()
def clean(book_slug: str) -> None:
    """Stage 2: Clean chapter files (remove watermarks, page numbers).

    Reads from chapters/, writes to cleaned/.
    """
    ...


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
