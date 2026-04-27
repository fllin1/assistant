"""Rewrite POV-character-attributed long dialogue blocks to "Narrator".

When the parser mis-tags a long block of first-person inner monologue or
exposition as `segment_type: dialogue`, the attribution model sometimes
labels it with the POV character's name instead of "Narrator". The
project convention is that mis-tagged narration belongs to "Narrator".

This script walks `reviewed/chapter_<id>.json` files for a slug and
rewrites any dialogue segment that matches ALL of:
  * `segment_type == "dialogue"`
  * `speaker` resolves (via the character registry) to the chapter's
    `pov_character`
  * `len(text) > threshold` (default 300)
  * the text shows a parser artifact: leading or trailing whitespace
    INSIDE the quote marks (`" foo "`), which only happens when the
    parser accidentally wrapped a multi-paragraph stretch of narration.
    Properly-quoted real dialogue (`"foo."`) is left alone.

The original speaker is recorded in a `normalisation` block appended to
the chapter's `*_report.json` sidecar so the rewrite is auditable.

Usage:
    python -m automations.ln_voice_over.scripts.normalize_narration <slug>
        [--dry-run] [--threshold 300]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from automations.ln_voice_over.models import Chapter, SegmentType
from automations.ln_voice_over.project import load_characters
from automations.ln_voice_over.split import chapter_id

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"


def _load_pov_map(manifest_path: Path) -> dict[str, str | None]:
    """Map chapter_id (e.g. '02', '07_1') → pov_character from the manifest.

    The parsed/reviewed Chapter JSONs sometimes carry a stale `pov_character`
    of None (the parse stage doesn't pull from the manifest). The manifest is
    the source of truth.
    """
    if not manifest_path.exists():
        return {}
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {chapter_id(e): e.get("pov_character") for e in entries}


def _canonical_pov(pov_character: str | None, registry) -> str | None:
    """Resolve the POV character against the registry to its canonical name."""
    if not pov_character:
        return None
    char = registry.find(pov_character) or registry.fuzzy_find(pov_character)
    return char.name if char else pov_character


def _canonicalise_speaker(raw: str | None, registry) -> str | None:
    """Canonicalise an arbitrary speaker label so equality with the POV name works."""
    if not raw or raw in ("Narrator", "Unknown", "I"):
        return raw
    char = registry.find(raw) or registry.fuzzy_find(raw)
    return char.name if char else raw


def _looks_like_mistagged_narration(text: str) -> bool:
    """A 'dialogue' text whose quote marks have whitespace immediately inside.

    Real dialogue: `"What did you do?"` — no whitespace adjacent to the quotes.
    Parser artifact: `" Then he walked away. "` — leading/trailing whitespace
    inside the quotes, the parser collapsed several segments together.
    """
    stripped = text.strip()
    if len(stripped) < 2:
        return False
    if stripped[0] != '"' or stripped[-1] != '"':
        return False  # not a quoted span at all; out of scope here
    inner = stripped[1:-1]
    return inner != inner.strip()


def _normalise_chapter(
    chapter_path: Path,
    report_path: Path,
    threshold: int,
    registry,
    pov_map: dict[str, str | None],
    dry_run: bool,
) -> list[dict]:
    """Return the list of rewrites applied (or that would be) for one chapter."""
    chapter = Chapter.load(chapter_path)
    # Manifest is the source of truth; fall back to the chapter's stored value.
    pov_raw = pov_map.get(chapter.chapter_id, chapter.pov_character)
    canonical_pov = _canonical_pov(pov_raw, registry)
    if not canonical_pov:
        return []  # third-person chapter: nothing to do

    rewrites: list[dict] = []
    new_segments = []
    for seg in chapter.segments:
        if (
            seg.segment_type == SegmentType.DIALOGUE
            and seg.speaker
            and len(seg.text) > threshold
            and _canonicalise_speaker(seg.speaker, registry) == canonical_pov
            and _looks_like_mistagged_narration(seg.text)
        ):
            rewrites.append({"index": seg.index, "old": seg.speaker, "new": "Narrator"})
            new_segments.append(seg.model_copy(update={"speaker": "Narrator"}))
        else:
            new_segments.append(seg)

    if not rewrites or dry_run:
        return rewrites

    rewritten = chapter.model_copy(update={"segments": tuple(new_segments)})
    rewritten.save(chapter_path)

    # Append normalisation block to existing sidecar (or create one).
    report_data: dict = {}
    if report_path.exists():
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
    report_data.setdefault("normalisation", []).extend(rewrites)
    report_path.write_text(
        json.dumps(report_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return rewrites


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("slug", help="<series>/<volume>")
    parser.add_argument(
        "--threshold",
        type=int,
        default=300,
        help="Minimum text length (chars) to consider a dialogue segment as mis-tagged narration.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would change; don't write files."
    )
    args = parser.parse_args()

    reviewed_dir = PROJECTS_DIR / args.slug / "reviewed"
    if not reviewed_dir.exists():
        print(f"ERROR: No reviewed/ directory for {args.slug}: {reviewed_dir}", file=sys.stderr)
        sys.exit(1)

    series_slug = args.slug.rsplit("/", 1)[0] if "/" in args.slug else args.slug
    registry = load_characters(series_slug)
    pov_map = _load_pov_map(PROJECTS_DIR / args.slug / "chapters" / "manifest.json")

    chapter_files = sorted(
        p for p in reviewed_dir.glob("chapter_*.json") if "_report" not in p.name
    )

    total_rewrites = 0
    per_chapter: dict[str, list[dict]] = {}
    for chapter_path in chapter_files:
        report_path = chapter_path.with_name(chapter_path.stem + "_report.json")
        rewrites = _normalise_chapter(
            chapter_path, report_path, args.threshold, registry, pov_map, args.dry_run
        )
        if rewrites:
            per_chapter[chapter_path.stem] = rewrites
            total_rewrites += len(rewrites)

    print(
        json.dumps(
            {
                "slug": args.slug,
                "threshold": args.threshold,
                "dry_run": args.dry_run,
                "total_rewrites": total_rewrites,
                "chapters": per_chapter,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
