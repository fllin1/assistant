"""Prepare chapter chunks for parallel speaker attribution.

Reads a parsed chapter JSON, splits segments into overlapping chunks,
writes each chunk to a temp directory, and prints metadata as JSON.

Usage:
    python -m automations.ln_voice_over.scripts.prepare_chunks <slug> <chapter_number>
"""

import json
import sys
from pathlib import Path

from automations.ln_voice_over.models import Chapter, SegmentType
from automations.ln_voice_over.split import chapter_id, normalize_chapter_arg

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"
CHUNK_SIZE = 80
OVERLAP = 20


def main():
    slug = sys.argv[1]
    chapter_raw = sys.argv[2]

    project_dir = PROJECTS_DIR / slug
    parsed_dir = project_dir / "parsed"

    padded = normalize_chapter_arg(chapter_raw)
    candidates = [
        parsed_dir / f"chapter_{chapter_raw}.json",
        parsed_dir / f"chapter_{padded}.json",
    ]
    chapter_path = next((p for p in candidates if p.exists()), None)
    if not chapter_path:
        print(f"ERROR: No chapter file found for '{chapter_raw}' in {parsed_dir}", file=sys.stderr)
        sys.exit(1)

    # Read manifest for the chapter narrator.
    manifest_path = project_dir / "chapters" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    entry = next((e for e in manifest if chapter_id(e) == padded), None)
    if entry is None:
        print(f"ERROR: Chapter '{chapter_raw}' not in manifest", file=sys.stderr)
        sys.exit(1)
    narrator_status = entry["narrator_status"]
    narrator = entry.get("narrator")

    # Load chapter via model
    chapter = Chapter.load(chapter_path)
    segments = chapter.segments
    total = len(segments)
    dialogue_count = sum(1 for s in segments if s.segment_type == SegmentType.DIALOGUE)

    # Split into chunks with overlap — write as raw JSON dicts for agent consumption
    tmp_dir = project_dir / "tmp_chunks"
    tmp_dir.mkdir(exist_ok=True)

    chunks = []
    start = 0
    chunk_idx = 0
    while start < total:
        end = min(start + CHUNK_SIZE, total)
        chunk_segments = [s.model_dump() for s in segments[start:end]]
        # Serialize enum values for agent readability
        for s in chunk_segments:
            s["segment_type"] = s["segment_type"].value

        chunk_path = tmp_dir / f"chunk_{chunk_idx}.json"
        output_path = tmp_dir / f"chunk_{chunk_idx}_output.json"

        chunk_path.write_text(json.dumps(chunk_segments, indent=2, ensure_ascii=False))

        chunks.append(
            {
                "chunk_idx": chunk_idx,
                "chunk_path": str(chunk_path),
                "output_path": str(output_path),
                "start_index": segments[start].index,
                "end_index": segments[end - 1].index,
            }
        )

        chunk_idx += 1
        start += CHUNK_SIZE - OVERLAP

    # Chapter number for file naming (preserve as-is for alphanumeric like "04a")
    chapter_file_id = chapter_path.stem.replace("chapter_", "")

    result = {
        "slug": slug,
        "chapter_raw": chapter_raw,
        "chapter_file_id": chapter_file_id,
        "narrator_status": narrator_status,
        "narrator": narrator,
        "total_segments": total,
        "dialogue_count": dialogue_count,
        "chunks": chunks,
        "tmp_dir": str(tmp_dir),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
