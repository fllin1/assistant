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

from .project import load_characters, resolve_volume

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
voice_map_app = typer.Typer(help="Manage accepted series voice mappings.")
app.add_typer(voice_map_app, name="voice-map")


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


@voice_map_app.command("import")
def import_voice_map(
    series: str = typer.Argument(..., help="Series slug, e.g. classroom-of-the-elite-year-2"),
    voice_tuning_root: str | None = typer.Option(
        None,
        "--voice-tuning-root",
        help="Path to the companion voice-tuning project.",
    ),
) -> None:
    """Import accepted voice-tuning cast rows into series voice_mapping.json."""
    from pathlib import Path

    from .voice_mapping import (
        DEFAULT_VOICE_TUNING_ROOT,
        import_voice_mapping_from_voice_tuning,
        save_voice_mapping,
        voice_mapping_path,
    )

    root = Path(voice_tuning_root) if voice_tuning_root else DEFAULT_VOICE_TUNING_ROOT
    registry = load_characters(series)
    mapping = import_voice_mapping_from_voice_tuning(registry, root)
    output_path = voice_mapping_path(series)
    save_voice_mapping(output_path, mapping)
    typer.echo(f"Wrote {len(mapping)} voice mapping entries → {output_path}")


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


@app.command()
def synthesize(
    book: str = typer.Argument(..., help="Volume slug, e.g. classroom-of-the-elite-year-2/v7"),
    chapter_id: str = typer.Argument(..., help="Chapter id, e.g. 01, 04_1, or chapter_01"),
    voice_tuning_root: str | None = typer.Option(
        None,
        "--voice-tuning-root",
        help="Path to the companion voice-tuning project.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Render without prompting."),
) -> None:
    """Stage 5: Render a reviewed chapter to WAV audio."""
    from pathlib import Path

    from .models import Chapter
    from .synthesis import (
        SynthesisError,
        SynthesisPreflightError,
        VoiceTuningBridge,
        build_synthesis_plan,
        format_render_plan,
        render_synthesis_plan,
        reviewed_chapter_path,
    )
    from .voice_mapping import DEFAULT_VOICE_TUNING_ROOT, load_voice_mapping, voice_mapping_path

    resolved = resolve_volume(book)
    registry = load_characters(resolved.series_slug)
    chapter_path = reviewed_chapter_path(resolved.volume_path, chapter_id)
    if not chapter_path.exists():
        typer.echo(f"No reviewed chapter found at {chapter_path}")
        raise typer.Exit(1)

    root = Path(voice_tuning_root) if voice_tuning_root else DEFAULT_VOICE_TUNING_ROOT
    bridge = VoiceTuningBridge(root)
    try:
        engine_infos = bridge.inspect_engines()
        plan = build_synthesis_plan(
            Chapter.load(chapter_path),
            registry,
            load_voice_mapping(voice_mapping_path(resolved.series_slug)),
            resolved.volume_path,
            chapter_id,
            engine_infos,
        )
    except SynthesisPreflightError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    except SynthesisError as exc:
        typer.echo(f"SYNTHESIS failed: {exc}")
        raise typer.Exit(1) from exc

    typer.echo(format_render_plan(plan))
    if not yes and not typer.confirm("Render audio now?"):
        typer.echo("Aborted before rendering.")
        raise typer.Exit(0)

    try:
        render_synthesis_plan(plan, bridge, progress=_echo_synthesis_progress)
    except SynthesisError as exc:
        typer.echo(f"SYNTHESIS failed: {exc}")
        raise typer.Exit(1) from exc
    typer.echo(f"Wrote {plan.output_path}")


def _echo_synthesis_progress(event: dict[str, object]) -> None:
    """Print concise terminal progress for synthesis rendering."""
    event_name = event.get("event")
    if event_name == "render_batch_start":
        typer.echo(f"Rendering {event['total']} uncached segment(s)...")
    elif event_name == "render_batch_cached":
        typer.echo("All TTS stems are cached; rebuilding chapter WAV...")
    elif event_name == "render_segment_start":
        typer.echo(
            "Rendering "
            f"{event['ordinal']}/{event['total']}: "
            f"segment {event['index']} "
            f"({event['engine']}, {event.get('voice_key')}, {event['text_chars']} chars)"
        )
    elif event_name == "render_batch_done":
        typer.echo("Voice generation complete; writing cache files...")
    elif event_name == "stems_start":
        typer.echo("Refreshing chapter stems...")
    elif event_name == "concat_start":
        typer.echo(f"Concatenating {event['output']}")


if __name__ == "__main__":
    app()
