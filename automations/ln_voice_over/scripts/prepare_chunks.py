"""Prepare chapter chunks for parallel speaker attribution.

Reads a parsed chapter JSON, splits segments into overlapping chunks,
writes each chunk to a temp directory, and prints metadata as JSON.

Usage:
    python prepare_chunks.py <slug> <chapter_number>
"""

import json
import sys
from pathlib import Path

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"
CHUNK_SIZE = 80
OVERLAP = 20


def main():
    slug = sys.argv[1]
    chapter_raw = sys.argv[2]

    # Resolve chapter file — try raw, then zero-padded
    project_dir = PROJECTS_DIR / slug
    parsed_dir = project_dir / "parsed"

    # Zero-pad numeric prefix: "4b" → "04b", "4" → "04", "12" → "12"
    import re

    match = re.match(r"^(\d+)(.*)", chapter_raw)
    padded = match.group(1).zfill(2) + match.group(2) if match else chapter_raw

    candidates = [
        parsed_dir / f"chapter_{chapter_raw}.json",
        parsed_dir / f"chapter_{padded}.json",
    ]
    chapter_path = next((p for p in candidates if p.exists()), None)
    if not chapter_path:
        print(f"ERROR: No chapter file found for '{chapter_raw}' in {parsed_dir}", file=sys.stderr)
        sys.exit(1)

    # Read manifest for POV character
    manifest_path = project_dir / "chapters" / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    pov_character = None
    for entry in manifest:
        if str(entry["number"]) == chapter_raw:
            pov_character = entry["pov_character"]
            break
    if not pov_character:
        print(f"ERROR: Chapter '{chapter_raw}' not found in manifest", file=sys.stderr)
        sys.exit(1)

    # Load chapter
    with open(chapter_path) as f:
        data = json.load(f)
    segments = data["segments"]
    total = len(segments)
    dialogue_count = sum(1 for s in segments if s.get("segment_type") == "dialogue")

    # Split into chunks with overlap
    tmp_dir = project_dir / "tmp_chunks"
    tmp_dir.mkdir(exist_ok=True)

    chunks = []
    start = 0
    chunk_idx = 0
    while start < total:
        end = min(start + CHUNK_SIZE, total)
        chunk_segments = segments[start:end]
        chunk_path = tmp_dir / f"chunk_{chunk_idx}.json"
        output_path = tmp_dir / f"chunk_{chunk_idx}_output.json"

        with open(chunk_path, "w") as f:
            json.dump(chunk_segments, f, indent=2)

        chunks.append(
            {
                "chunk_idx": chunk_idx,
                "chunk_path": str(chunk_path),
                "output_path": str(output_path),
                "start_index": segments[start]["index"],
                "end_index": segments[end - 1]["index"],
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
        "pov_character": pov_character,
        "total_segments": total,
        "dialogue_count": dialogue_count,
        "chunks": chunks,
        "tmp_dir": str(tmp_dir),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
