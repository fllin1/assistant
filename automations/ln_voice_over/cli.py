"""CLI interface for the LN voice-over pipeline.

Typer app with one command per implemented pipeline stage. Each command
reads from the appropriate volume subdirectory and writes to its own
output directory. Running `lnvo` alone opens an interactive picker.

Every command accepts a positional `book` argument in one of three forms:
  * ``<series>/<volume>`` — canonical nested form (e.g. ``cote-y2/v7``).
  * ``<series>-v<N>`` — legacy flat slug (still works; auto-split).
  * ``<series>`` — implies volume ``v1`` for standalone books.

Omit the argument to get an interactive picker over existing projects.
"""

from __future__ import annotations

import typer
from dotenv import load_dotenv

from .project import resolve_volume

# Load .env if present. No-op when absent; kept for future callers.
load_dotenv()

app = typer.Typer(
    name="lnvo",
    help=(
        "Light novel → attributed-chapters pipeline.\n\n"
        "Full flow (run these in order for a volume):\n"
        "  1. /setup-book <url> <series>/<volume>   — source skill (PDF → book.json)\n"
        "  2. lnvo split <series>/<volume>          — chapters/\n"
        "  3. lnvo parse <series>/<volume>          — parsed/\n"
        "  4. /attribute-speakers <slug> <chapter>  — speaker attribution skill\n"
        "  5. /review-attribution <slug> <chapter>  — judge + Opus review skill\n"
        "Output: <volume>/reviewed/chapter_NN.json"
    ),
)


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    """Guided menu when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        from .interactive import interactive_menu

        interactive_menu()


@app.command()
def list_books() -> None:
    """List all projects grouped as `<series>/<volume>`."""
    from .project import list_series, list_volumes

    any_found = False
    for series_slug in list_series():
        volumes = list_volumes(series_slug)
        if not volumes:
            typer.echo(f"{series_slug}/ (no volumes)")
            continue
        for vol in volumes:
            typer.echo(f"{series_slug}/{vol}")
            any_found = True
    if not any_found:
        typer.echo("(no projects found)")


@app.command()
def split(book: str | None = typer.Argument(None)) -> None:
    """Stage 1: Split a volume into chapter files.

    Reads from volume source/, accepting two formats (checked in order):
    1. source/book.json — pre-structured JSON from /setup-book skill
    2. source/*.txt — raw volume text file (regex-based splitting)
    """
    from .init_project import migrate_source_dir
    from .interactive import resolve_book_arg
    from .split import split_volume, write_manifest

    resolved = resolve_volume(resolve_book_arg(book))
    root = resolved.volume_path
    migrate_source_dir(root)

    source_dir = root / "source"
    output_dir = root / "chapters"

    # Try JSON first (from PDF extraction), fall back to .txt
    book_json = source_dir / "book.json"
    if book_json.exists():
        source = book_json
        typer.echo(f"Using extracted book: {source}")
    else:
        txt_files = sorted(source_dir.glob("*.txt"))
        if not txt_files:
            typer.echo(f"No book.json or .txt files found in {source_dir}")
            raise typer.Exit(1)
        source = txt_files[0]
        if len(txt_files) > 1:
            typer.echo(f"Multiple .txt files found, using: {source.name}")

    chapters = split_volume(source, output_dir)
    write_manifest(chapters, output_dir)
    typer.echo(f"Split into {len(chapters)} chapter(s) → {output_dir}")


@app.command()
def parse(book: str | None = typer.Argument(None)) -> None:
    """Stage 2: Parse chapter text into typed segments (includes cleanup)."""
    import json

    from .interactive import resolve_book_arg
    from .parse import parse_chapter

    resolved = resolve_volume(resolve_book_arg(book))
    root = resolved.volume_path
    chapters_dir = root / "chapters"
    output_dir = root / "parsed"
    manifest_path = chapters_dir / "manifest.json"

    if not manifest_path.exists():
        typer.echo(f"No manifest found at {manifest_path}. Run 'split' first.")
        raise typer.Exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)

    from .split import chapter_id

    count = 0
    for entry in manifest:
        if "narrator_status" not in entry:
            typer.echo(
                "Manifest uses the old narrator schema. "
                "Run migrate_narrator_fields before parsing."
            )
            raise typer.Exit(1)
        chapter_path = chapters_dir / entry["file"]
        if not chapter_path.exists():
            typer.echo(f"Skipping {entry['file']} — not found in chapters/")
            continue

        chapter = parse_chapter(
            chapter_path,
            chapter_number=entry["number"],
            subchapter=entry.get("subchapter"),
            title=entry["title"],
            narrator_status=entry["narrator_status"],
            narrator=entry.get("narrator"),
        )
        chapter.save(output_dir / f"chapter_{chapter_id(entry)}.json")
        count += 1

    typer.echo(f"Parsed {count} chapter(s) → {output_dir}")


if __name__ == "__main__":
    app()
