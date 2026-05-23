"""Prepare narrator detection for a chapter.

Reads the manifest and parsed chapter. If narrator detection has already run,
reports that and exits. Otherwise, writes the chapter's opening snippet to a
temp file and prints the paths the skill needs to run an LLM agent on it.

Usage:
    python -m automations.ln_voice_over.scripts.detect_narrator <slug> <chapter_number>
"""

import json
import sys
from pathlib import Path

from automations.ln_voice_over.models import Chapter, SegmentType
from automations.ln_voice_over.split import chapter_id, normalize_chapter_arg

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"
SNIPPET_MAX_CHARS = 3000


def main() -> None:
    slug = sys.argv[1]
    chapter_raw = sys.argv[2]

    project_dir = PROJECTS_DIR / slug
    parsed_dir = project_dir / "parsed"
    manifest_path = project_dir / "chapters" / "manifest.json"

    padded = normalize_chapter_arg(chapter_raw)
    candidates = [
        parsed_dir / f"chapter_{chapter_raw}.json",
        parsed_dir / f"chapter_{padded}.json",
    ]
    chapter_path = next((p for p in candidates if p.exists()), None)
    if not chapter_path:
        print(f"ERROR: No chapter file found for '{chapter_raw}' in {parsed_dir}", file=sys.stderr)
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next((e for e in manifest if chapter_id(e) == padded), None)
    if entry is None:
        print(f"ERROR: Chapter '{chapter_raw}' not in manifest", file=sys.stderr)
        sys.exit(1)

    chapter_title = entry.get("title", "")
    narrator_status = entry.get("narrator_status")
    if narrator_status != "unset" and narrator_status != "detected":
        print(
            f"ERROR: Chapter '{chapter_raw}' has invalid narrator_status={narrator_status!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    if narrator_status == "detected":
        print(
            json.dumps(
                {
                    "status": "already_detected",
                    "narrator_status": narrator_status,
                    "narrator": entry.get("narrator"),
                    "chapter_number": chapter_raw,
                    "chapter_title": chapter_title,
                    "manifest_path": str(manifest_path),
                }
            )
        )
        return

    # Build the opening snippet from narration + dialogue, skipping headers and scene breaks.
    chapter = Chapter.load(chapter_path)
    parts: list[str] = []
    total = 0
    for seg in chapter.segments:
        if seg.segment_type in (SegmentType.CHAPTER_HEADER, SegmentType.SCENE_BREAK):
            continue
        parts.append(seg.text)
        total += len(seg.text) + 2
        if total >= SNIPPET_MAX_CHARS:
            break

    tmp_dir = project_dir / "tmp_chunks"
    tmp_dir.mkdir(exist_ok=True)
    snippet_path = tmp_dir / f"narrator_snippet_{chapter_raw}.txt"
    snippet_path.write_text("\n\n".join(parts), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "needs_detection",
                "snippet_path": str(snippet_path),
                "manifest_path": str(manifest_path),
                "chapter_number": chapter_raw,
                "chapter_title": chapter_title,
            }
        )
    )


if __name__ == "__main__":
    main()
