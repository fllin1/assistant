"""Batch extraction script: run models across all chapters.

Supports Gemini Flash (OpenRouter) and Gemma4 (Ollama). Claude Sonnet
runs are handled separately via the /attribute-chapter skill.

Runs one chapter at a time per model to avoid overloading APIs.

Usage:
    # Run all models on all chapters
    python -m automations.ln_voice_over.scripts.run_all_extractions

    # Run only Gemini Flash
    python -m automations.ln_voice_over.scripts.run_all_extractions --model gemini-flash

    # Run specific chapters
    python -m automations.ln_voice_over.scripts.run_all_extractions \
        --model gemma4:26b --chapters 1,3,5

    # Resolve only (skip extraction)
    python -m automations.ln_voice_over.scripts.run_all_extractions --resolve-only
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys

from automations.ln_voice_over.config import MODEL_REGISTRY, PROJECTS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

BOOK_SLUG = "classroom-of-the-elite-year-2"

# All chapter identifiers (includes 4a/4b split)
ALL_CHAPTERS = ["1", "2", "3", "4a", "4b", "5", "6", "7", "8", "9"]

# POV characters per chapter (from manifest)
POV_MAP = {
    "1": "Hasebe Haruka",
    "2": "Ayanokouji Kiyotaka",
    "3": "Ayanokouji Kiyotaka",
    "4a": "Ayanokouji Kiyotaka",
    "4b": "Horikita Suzune",
    "5": "Ayanokouji Kiyotaka",
    "6": "Ayanokouji Kiyotaka",
    "7": "Ayanokouji Kiyotaka",
    "8": "Horikita Suzune",
    "9": "Ayanokouji Kiyotaka",
}

# Default models when none specified
DEFAULT_MODELS = ["gemini-flash", "gemma4:26b"]


def chapter_file_id(ch: str) -> str:
    """Convert chapter identifier to file-safe format: '4a' → '04a', '3' → '03'."""
    if ch[-1].isalpha():
        return f"{int(ch[:-1]):02d}{ch[-1]}"
    return f"{int(ch):02d}"


def run_extraction(model: str, chapter: str, book_slug: str) -> tuple[str, str, bool, str]:
    """Run a single extraction via CLI subprocess."""
    pov = POV_MAP[chapter]
    file_id = chapter_file_id(chapter)
    cmd = [
        sys.executable,
        "-m",
        "automations.ln_voice_over.cli",
        "extract",
        book_slug,
        "--chapter",
        file_id,
        "--model",
        model,
        "--pov",
        pov,
        "--batch-size",
        "9999",
    ]
    logger.info("Starting: %s chapter %s", model, chapter)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    success = result.returncode == 0
    output = result.stdout.strip() if success else result.stderr.strip()
    if success:
        logger.info("Done: %s chapter %s", model, chapter)
    else:
        logger.error("FAILED: %s chapter %s\n%s", model, chapter, output)
    return model, chapter, success, output


def resolve_all(book_slug: str) -> None:
    """Resolve all chapters using available sources."""
    root = PROJECTS_DIR / book_slug
    extracted_base = root / "extracted"

    for chapter_dir in sorted(extracted_base.iterdir()):
        if not chapter_dir.is_dir():
            continue
        chapter_id = chapter_dir.name.replace("chapter_", "")
        sources = sorted(
            f.stem for f in chapter_dir.glob("*.json") if not f.stem.endswith("_config")
        )
        if not sources:
            continue

        logger.info("Resolving chapter %s with %d sources: %s", chapter_id, len(sources), sources)
        cmd = [
            sys.executable,
            "-m",
            "automations.ln_voice_over.cli",
            "resolve",
            book_slug,
            "--chapter",
            chapter_id,
            *[arg for s in sources for arg in ("--source", s)],
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("Resolved chapter %s: %s", chapter_id, result.stdout.strip())
        else:
            logger.error("Failed resolving chapter %s: %s", chapter_id, result.stderr.strip())


def diagnosis(book_slug: str) -> None:
    """Generate a diagnosis report across all chapters."""
    root = PROJECTS_DIR / book_slug
    attributed_dir = root / "attributed"
    extracted_dir = root / "extracted"

    report_lines = [
        "=" * 70,
        "DIAGNOSIS REPORT",
        "=" * 70,
        "",
    ]

    for ch in ALL_CHAPTERS:
        file_id = chapter_file_id(ch)
        chapter_path = attributed_dir / f"chapter_{file_id}.json"
        flags_path = attributed_dir / f"chapter_{file_id}_flags.json"
        extracted_chapter = extracted_dir / f"chapter_{file_id}"

        sources = list(extracted_chapter.glob("*.json")) if extracted_chapter.exists() else []

        if not chapter_path.exists():
            report_lines.append(f"Chapter {ch}: NOT RESOLVED")
            report_lines.append(f"  Sources: {len(sources)}")
            report_lines.append("")
            continue

        data = json.loads(chapter_path.read_text())
        segments = data["segments"]
        dialogues = [s for s in segments if s["segment_type"] == "dialogue"]
        attributed = sum(1 for d in dialogues if d.get("speaker"))
        unknown = sum(1 for d in dialogues if d.get("speaker") == "Unknown")

        flags = []
        if flags_path.exists():
            flags = json.loads(flags_path.read_text())

        flag_types: dict[str, int] = {}
        for f in flags:
            t = f.get("type", "other")
            flag_types[t] = flag_types.get(t, 0) + 1

        report_lines.append(f"Chapter {ch}: {attributed}/{len(dialogues)} dialogues attributed")
        report_lines.append(f"  Sources: {', '.join(s.stem for s in sources)}")
        report_lines.append(f"  Unknown: {unknown}")
        report_lines.append(f"  Flags: {len(flags)} ({flag_types})")
        if flags:
            for f in flags[:5]:
                report_lines.append(
                    f"    - [{f.get('index')}] {f.get('type')}: {f.get('raw', f.get('value', ''))}"
                )
            if len(flags) > 5:
                report_lines.append(f"    ... and {len(flags) - 5} more")
        report_lines.append("")

    report = "\n".join(report_lines)
    report_path = root / "diagnosis_report.txt"
    report_path.write_text(report + "\n")
    logger.info("\n%s", report)
    logger.info("Report saved to %s", report_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch extraction across chapters and models.")
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help=f"Model to run (repeatable). Known: {', '.join(sorted(MODEL_REGISTRY))}. "
        f"Default: {', '.join(DEFAULT_MODELS)}",
    )
    parser.add_argument(
        "--chapters",
        help=f"Comma-separated chapter list. Default: {','.join(ALL_CHAPTERS)}",
    )
    parser.add_argument(
        "--resolve-only",
        action="store_true",
        help="Skip extraction, only resolve + diagnose.",
    )
    parser.add_argument(
        "--no-resolve",
        action="store_true",
        help="Run extraction only, skip resolve and diagnosis.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    models = args.models or DEFAULT_MODELS
    chapters = args.chapters.split(",") if args.chapters else ALL_CHAPTERS

    # Validate models
    for m in models:
        if m not in MODEL_REGISTRY:
            logger.error("Unknown model '%s'. Known: %s", m, ", ".join(sorted(MODEL_REGISTRY)))
            sys.exit(1)

    # Validate chapters
    for ch in chapters:
        if ch not in ALL_CHAPTERS:
            logger.error("Unknown chapter '%s'. Known: %s", ch, ", ".join(ALL_CHAPTERS))
            sys.exit(1)

    logger.info("Book: %s", BOOK_SLUG)
    logger.info("Models: %s", ", ".join(models))
    logger.info("Chapters: %s", ", ".join(chapters))

    if not args.resolve_only:
        results = []
        for model in models:
            for ch in chapters:
                model_name, chapter, success, output = run_extraction(model, ch, BOOK_SLUG)
                results.append((model_name, chapter, success, output))

        succeeded = sum(1 for _, _, ok, _ in results if ok)
        failed = sum(1 for _, _, ok, _ in results if not ok)
        logger.info("Extraction complete: %d succeeded, %d failed", succeeded, failed)

        for model, chapter, ok, output in sorted(results):
            if not ok:
                logger.error("  FAILED: %s chapter %s: %s", model, chapter, output[:200])

    if not args.no_resolve:
        logger.info("Resolving all chapters...")
        resolve_all(BOOK_SLUG)

        logger.info("Generating diagnosis...")
        diagnosis(BOOK_SLUG)


if __name__ == "__main__":
    main()
