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

import typing

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
    """Stage 1: Split a volume into chapter files.

    Accepts two input formats (checked in order):
    1. downloads/book.json — pre-structured JSON from /extract-book skill
    2. raw/*.txt — raw volume text file (regex-based splitting)

    Outputs chapter files and manifest.json to:
        ~/.assistant/ln_voice_over/projects/<book-slug>/chapters/
    """
    from .split import split_volume, write_manifest

    root = PROJECTS_DIR / book_slug
    output_dir = root / "chapters"

    # Try JSON first (from PDF extraction), fall back to .txt
    book_json = root / "downloads" / "book.json"
    if book_json.exists():
        source = book_json
        typer.echo(f"Using extracted book: {source}")
    else:
        raw_dir = root / "raw"
        txt_files = sorted(raw_dir.glob("*.txt"))
        if not txt_files:
            typer.echo(f"No book.json in downloads/ and no .txt files in {raw_dir}")
            raise typer.Exit(1)
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
        chapter.save(output_dir / f"chapter_{entry['number']:02d}.json")
        count += 1

    typer.echo(f"Parsed {count} chapter(s) → {output_dir}")


@app.command(name="extract")
def extract(
    book_slug: str,
    chapter: str = typer.Option(..., help="Chapter ID (e.g. 2, 04a)."),
    model: str = typer.Option("gemma4:26b", help="Model (Ollama or OpenRouter)."),
    context_before: int = typer.Option(10, "--context-before", help="Segments before dialogue."),
    context_after: int = typer.Option(5, "--context-after", help="Segments after dialogue."),
    batch_start: int = typer.Option(0, "--batch-start", help="Start index in dialogue list."),
    batch_size: int = typer.Option(100, "--batch-size", help="Number of dialogues per batch."),
    pov_character: str | None = typer.Option(None, "--pov", help="Override POV character name."),
    rolling_context: bool = typer.Option(
        True, "--rolling-context", help="Pass recent attributions as context."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", help="Verbose mode: LLM returns speaker + reasoning JSON."
    ),
) -> None:
    """Run Step 1: speaker mention extraction.

    Extracts who speaks each dialogue using LLM analysis of narration context.
    Results saved to extracted/chapter_NN/<model>_<mode>_<date>.json.
    """
    import logging

    from .experiments.runner import run_extraction_experiment
    from .extraction import ExtractionConfig

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    config = ExtractionConfig(
        model=model,
        context_before=context_before,
        context_after=context_after,
        pov_character=pov_character,
        use_rolling_context=rolling_context,
        fast=not verbose,
    )
    extracted_path = run_extraction_experiment(
        book_slug=book_slug,
        chapter_id=chapter,
        config=config,
        batch_start=batch_start,
        batch_size=batch_size,
    )
    typer.echo(f"Extraction saved → {extracted_path}")


@app.command(name="resolve")
def resolve(
    book_slug: str,
    chapter: str = typer.Option(..., help="Chapter ID (e.g. 2, 04a)."),
    source: typing.Annotated[
        list[str],
        typer.Option(
            "--source", help="Source filenames in extracted/chapter_NN/ (without .json)."
        ),
    ] = ...,
) -> None:
    """Resolve raw speaker names to canonical character names.

    Loads extraction results from extracted/chapter_NN/, resolves names
    against the character registry, and writes resolved chapter + flags.
    """
    import json
    import logging

    from .models import Chapter, CharacterRegistry
    from .resolution import cross_validate, load_extracted, resolve_chapter

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    root = PROJECTS_DIR / book_slug
    parsed_path = root / "parsed" / f"chapter_{chapter}.json"
    extracted_dir = root / "extracted" / f"chapter_{chapter}"
    registry_path = root / "config" / "characters.json"
    output_dir = root / "resolved"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not parsed_path.exists():
        typer.echo(f"Parsed chapter not found: {parsed_path}")
        raise typer.Exit(1)
    if not registry_path.exists():
        typer.echo(f"Character registry not found: {registry_path}")
        raise typer.Exit(1)

    ch = Chapter.load(parsed_path)
    registry = CharacterRegistry.load(registry_path)

    # Load sources
    sources: dict[str, dict[str, str]] = {}
    for s in source:
        path = extracted_dir / f"{s}.json"
        if not path.exists():
            typer.echo(f"Source not found: {path}")
            raise typer.Exit(1)
        sources[s] = load_extracted(path)
        typer.echo(f"Loaded {s}: {len(sources[s])} entries")

    # Cross-validate if multiple sources, otherwise use single source directly
    confirmed_unknowns: set[str] = set()
    if len(sources) > 1:
        attributions, divergences, confirmed_unknowns = cross_validate(sources, registry)
        typer.echo(f"Cross-validation: {len(divergences)} divergences")
    else:
        attributions = next(iter(sources.values()))
        divergences = []

    # Resolve names to canonical
    attributed, flags = resolve_chapter(
        ch, attributions, registry, confirmed_unknowns=confirmed_unknowns
    )
    flags.extend(divergences)

    # Save
    out_path = output_dir / f"chapter_{chapter}.json"
    attributed.save(out_path)
    typer.echo(f"Attributed chapter → {out_path}")

    if flags:
        flags_path = output_dir / f"chapter_{chapter}_flags.json"
        flags_path.write_text(
            json.dumps(flags, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        typer.echo(f"{len(flags)} flags → {flags_path}")
    else:
        typer.echo("No flags — all attributions resolved cleanly.")


@app.command()
def review(
    book_slug: str,
    chapter: int | None = typer.Option(None, help="Review only this chapter."),
    approve_all: bool = typer.Option(False, help="Approve all without review."),
) -> None:
    """Stage 5: Review and correct speaker attributions.

    Reads from resolved/, writes to reviewed/.
    """
    ...


# ---------------------------------------------------------------------------
# Voice management commands
# ---------------------------------------------------------------------------


@app.command(name="list-voices")
def list_voices(
    provider_name: str = typer.Option(
        "edge", "--provider", help="TTS provider (edge/openai/kokoro)."
    ),
    gender: str | None = typer.Option(None, help="Filter by gender (male/female)."),
    locale: str = typer.Option("en-", help="Locale prefix filter (Edge only)."),
) -> None:
    """List available TTS voices."""
    if provider_name == "openai":
        from .providers.openai import OPENAI_VOICES

        voices = OPENAI_VOICES
        if gender:
            voices = [v for v in voices if v["gender"].lower() == gender.lower()]
        for v in voices:
            typer.echo(f"  {v['voice_id']:20s} {v['gender']:8s} {v['description']}")
        typer.echo(f"\n{len(voices)} voice(s)")
    elif provider_name == "kokoro":
        from .providers.kokoro import KOKORO_VOICES

        voices = KOKORO_VOICES
        if gender:
            voices = [v for v in voices if v["gender"].lower() == gender.lower()]
        for v in voices:
            typer.echo(
                f"  {v['voice_id']:20s} {v['gender']:8s} {v['accent']:10s} {v['description']}"
            )
        typer.echo(f"\n{len(voices)} voice(s)")
    else:
        import asyncio

        from .providers.edge import list_edge_voices

        edge_voices = asyncio.run(list_edge_voices(locale_prefix=locale, gender=gender))
        if not edge_voices:
            typer.echo("No voices found matching filters.")
            raise typer.Exit(1)

        for v in sorted(edge_voices, key=lambda x: (x["Locale"], x["Gender"], x["ShortName"])):
            typer.echo(f"  {v['ShortName']:35s} {v['Gender']:8s} {v['Locale']}")
        typer.echo(f"\n{len(edge_voices)} voice(s)")


@app.command()
def audition(
    voice_id: str = typer.Argument(help="Voice name (e.g. en-US-GuyNeural, nova)."),
    text: str | None = typer.Option(None, help="Custom sample text."),
    character: str | None = typer.Option(None, help="Character name to find sample dialogue."),
    book: str | None = typer.Option(None, help="Book slug (required with --character)."),
    provider_name: str = typer.Option("edge", "--provider", help="TTS provider (edge/openai)."),
) -> None:
    """Preview a voice by synthesizing sample text and playing it."""
    import subprocess
    import tempfile

    from .providers.registry import get_provider

    sample = (
        text or "The quick brown fox jumps over the lazy dog. How fascinating, don't you think?"
    )

    # Find a real dialogue line from the character if requested
    if character and book:
        sample = _find_character_dialogue(book, character) or sample

    # Strip surrounding dialogue quotes — Edge TTS chokes on them
    if sample.startswith(("\u201c", '"')) and sample.endswith(("\u201d", '"')):
        sample = sample[1:-1]

    provider = get_provider(provider_name)
    typer.echo(f"Synthesizing with {voice_id} ({provider_name})...")
    typer.echo(f'  "{sample[:80]}{"..." if len(sample) > 80 else ""}"')

    audio = provider.synthesize(sample, voice_id)

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio)
        tmp_path = f.name

    subprocess.run(["afplay", tmp_path], check=True)


def _find_character_dialogue(book_slug: str, character_name: str) -> str | None:
    """Find a sample dialogue line from a character in resolved chapters."""
    from .models import Chapter

    root = PROJECTS_DIR / book_slug
    # Check reviewed first, then resolved
    for stage_dir in [root / "reviewed", root / "resolved"]:
        if not stage_dir.exists():
            continue
        for path in sorted(stage_dir.glob("chapter_*.json")):
            if path.name.endswith("_flags.json"):
                continue
            chapter = Chapter.load(path)
            for seg in chapter.segments:
                if (
                    seg.speaker
                    and seg.speaker.lower() == character_name.lower()
                    and len(seg.text) > 20
                ):
                    return seg.text
    return None


@app.command(name="assign-voice")
def assign_voice(
    book_slug: str,
    character_name: str = typer.Argument(help="Character name (as in characters.json)."),
    voice_id: str = typer.Argument(help="Edge voice ID (e.g. en-US-DavisNeural)."),
    provider_name: str = typer.Option("edge", help="TTS provider."),
) -> None:
    """Assign a TTS voice to a character."""
    from .models import CharacterRegistry, VoiceConfig, VoiceMapping

    root = PROJECTS_DIR / book_slug
    registry_path = root / "config" / "characters.json"
    voices_path = root / "config" / "voices.json"

    registry = CharacterRegistry.load(registry_path)
    char = registry.find(character_name)
    if not char:
        typer.echo(f"Character '{character_name}' not found in registry.")
        raise typer.Exit(1)

    config = VoiceConfig.load(voices_path)

    # Check for existing mapping
    existing = [m for m in config.mappings if m.speaker == char.name]
    if existing:
        typer.echo(f"Updating: {char.name} was {existing[0].voice_id} → {voice_id}")

    new_mapping = VoiceMapping(speaker=char.name, provider=provider_name, voice_id=voice_id)

    # Replace or append
    new_mappings = (*[m for m in config.mappings if m.speaker != char.name], new_mapping)
    config = config.model_copy(update={"mappings": new_mappings})

    config.save(voices_path)
    typer.echo(f"Assigned {char.name} → {voice_id} ({provider_name})")


@app.command(name="show-voices")
def show_voices(book_slug: str) -> None:
    """Show current voice assignments for a project."""
    from .models import CharacterRegistry, VoiceConfig

    root = PROJECTS_DIR / book_slug
    registry = CharacterRegistry.load(root / "config" / "characters.json")
    config = VoiceConfig.load(root / "config" / "voices.json")

    assigned_names = {m.speaker for m in config.mappings}

    # Assigned characters
    if config.mappings:
        typer.echo("Assigned:")
        for m in sorted(config.mappings, key=lambda x: x.speaker):
            typer.echo(f"  {m.speaker:30s} → {m.voice_id} ({m.provider})")
    else:
        typer.echo("No voices assigned yet.")

    # Unassigned, grouped by role
    unassigned_main = [
        c
        for c in registry.characters
        if c.name not in assigned_names and c.role in ("main", "supporting")
    ]
    unassigned_minor = [
        c for c in registry.characters if c.name not in assigned_names and c.role == "minor"
    ]

    if unassigned_main:
        typer.echo(f"\nUnassigned (main/supporting) — {len(unassigned_main)}:")
        for c in unassigned_main:
            fallback = config.get_voice(c.name, c.gender)
            typer.echo(f"  {c.name:30s} ({c.gender:6s}) → fallback: {fallback.voice_id}")

    if unassigned_minor:
        typer.echo(f"\nUnassigned (minor) — {len(unassigned_minor)}:")
        for c in unassigned_minor:
            fallback = config.get_voice(c.name, c.gender)
            typer.echo(f"  {c.name:30s} ({c.gender:6s}) → fallback: {fallback.voice_id}")

    # Defaults
    typer.echo("\nDefaults:")
    typer.echo(f"  Narrator:  {config.default_narrator.voice_id}")
    typer.echo(f"  Male:      {config.default_male.voice_id}")
    typer.echo(f"  Female:    {config.default_female.voice_id}")


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
