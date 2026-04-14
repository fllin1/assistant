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
    import json

    from .parse import parse_chapter
    from .serialization import save_chapter

    root = PROJECTS_DIR / book_slug
    cleaned_dir = root / "cleaned"
    output_dir = root / "parsed"
    manifest_path = root / "chapters" / "manifest.json"

    if not manifest_path.exists():
        typer.echo(f"No manifest found at {manifest_path}. Run 'split' first.")
        raise typer.Exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for entry in manifest:
        cleaned_path = cleaned_dir / entry["file"]
        if not cleaned_path.exists():
            typer.echo(f"Skipping {entry['file']} — not found in cleaned/")
            continue

        chapter = parse_chapter(
            cleaned_path,
            chapter_number=entry["number"],
            title=entry["title"],
            pov_character=entry.get("pov_character"),
        )
        save_chapter(chapter, output_dir / f"chapter_{entry['number']:02d}.json")
        count += 1

    typer.echo(f"Parsed {count} chapter(s) → {output_dir}")


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


@app.command(name="extract")
def extract(
    book_slug: str,
    chapter: int = typer.Option(..., help="Chapter number to process."),
    model: str = typer.Option("gemma4:26b", help="Ollama model tag."),
    prompt_version: str = typer.Option("v1", "--prompt-version", help="Prompt template version."),
    context_before: int = typer.Option(5, "--context-before", help="Segments before dialogue."),
    context_after: int = typer.Option(5, "--context-after", help="Segments after dialogue."),
    batch_start: int = typer.Option(0, "--batch-start", help="Start index in dialogue list."),
    batch_size: int = typer.Option(100, "--batch-size", help="Number of dialogues per batch."),
    pov_character: str | None = typer.Option(None, "--pov", help="Override POV character name."),
    rolling_context: bool = typer.Option(
        False, "--rolling-context", help="Pass recent attributions as context."
    ),
) -> None:
    """Run Step 1: speaker mention extraction experiment.

    Extracts who speaks each dialogue using LLM analysis of narration context.
    Results saved to experiments/extraction/<run_id>/.
    """
    import logging

    from .experiments.runner import run_extraction_experiment
    from .extraction import ExtractionConfig

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    config = ExtractionConfig(
        model=model,
        prompt_version=prompt_version,
        context_before=context_before,
        context_after=context_after,
        pov_character=pov_character,
        use_rolling_context=rolling_context,
    )
    exp_dir = run_extraction_experiment(
        book_slug=book_slug,
        chapter_num=chapter,
        config=config,
        batch_start=batch_start,
        batch_size=batch_size,
    )
    typer.echo(f"Experiment saved → {exp_dir}")


@app.command(name="compare")
def compare(
    book_slug: str,
    experiment_id: str = typer.Argument(..., help="Experiment directory name."),
) -> None:
    """Compare extraction experiment results against ground truth."""
    from .config import PROJECTS_DIR
    from .experiments.compare import compare_to_ground_truth, format_comparison_report

    root = PROJECTS_DIR / book_slug
    exp_dir = root / "experiments" / "extraction" / experiment_id
    gt_path = root / "ground_truth_chapter_02.json"
    registry_path = root / "config" / "characters.json"

    if not exp_dir.exists():
        typer.echo(f"Experiment not found: {exp_dir}")
        raise typer.Exit(1)
    if not gt_path.exists():
        typer.echo(f"Ground truth not found: {gt_path}")
        raise typer.Exit(1)

    comparison = compare_to_ground_truth(exp_dir, gt_path, registry_path)
    typer.echo(format_comparison_report(comparison))


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
