"""Prepare shifted-overlap chunks for the judge-pass re-attribution.

The judge re-attributes a chapter with different chunk boundaries than the
original `/attribute-speakers` pass so disagreements surface real uncertainty
rather than shared context. Concretely: the first chunk is half-width
(segments 0..40) and subsequent chunks run at the normal 80/20 cadence
offset by 40 (40..120, 100..180, ...). Output lands in
`judge/chapter_<id>/chunk_*.json` — a dedicated directory so /attribute-speakers
artefacts never collide with the judge's.

Usage:
    python -m automations.ln_voice_over.scripts.prepare_judge_chunks <slug> <chapter>
"""

import json
import sys
from pathlib import Path

from automations.ln_voice_over.models import Chapter, SegmentType
from automations.ln_voice_over.split import chapter_id, normalize_chapter_arg

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"
CHUNK_SIZE = 80
OVERLAP = 20
JUDGE_OFFSET = 40  # shift judge chunks by half a chunk-size vs the original pass


def main() -> None:
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
        print(f"ERROR: No parsed chapter for '{chapter_raw}' in {parsed_dir}", file=sys.stderr)
        sys.exit(1)

    manifest_path = project_dir / "chapters" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next((e for e in manifest if chapter_id(e) == padded), None)
    if entry is None:
        print(f"ERROR: Chapter '{chapter_raw}' not in manifest", file=sys.stderr)
        sys.exit(1)
    narrator_status = entry["narrator_status"]
    narrator = entry.get("narrator")

    chapter = Chapter.load(chapter_path)
    segments = chapter.segments
    total = len(segments)
    dialogue_count = sum(1 for s in segments if s.segment_type == SegmentType.DIALOGUE)

    judge_dir = project_dir / "judge" / f"chapter_{padded}"
    judge_dir.mkdir(parents=True, exist_ok=True)
    # Wipe any prior judge chunks so re-runs start clean.
    for old in judge_dir.glob("chunk_*.json"):
        old.unlink()

    # Produce shifted chunks: first is [0..JUDGE_OFFSET], rest run 80/20 starting at JUDGE_OFFSET.
    chunk_bounds: list[tuple[int, int]] = []
    if total <= JUDGE_OFFSET:
        chunk_bounds.append((0, total))
    else:
        chunk_bounds.append((0, JUDGE_OFFSET))
        start = JUDGE_OFFSET
        while start < total:
            end = min(start + CHUNK_SIZE, total)
            chunk_bounds.append((start, end))
            if end == total:
                break
            start += CHUNK_SIZE - OVERLAP

    chunks = []
    for idx, (start, end) in enumerate(chunk_bounds):
        chunk_segments = [s.model_dump() for s in segments[start:end]]
        for s in chunk_segments:
            s["segment_type"] = s["segment_type"].value

        chunk_path = judge_dir / f"chunk_{idx}.json"
        chunk_path.write_text(json.dumps(chunk_segments, indent=2, ensure_ascii=False))

        chunks.append(
            {
                "chunk_idx": idx,
                "chunk_path": str(chunk_path),
                "start_index": segments[start].index,
                "end_index": segments[end - 1].index,
            }
        )

    result = {
        "slug": slug,
        "chapter_raw": chapter_raw,
        "chapter_id": padded,
        "narrator_status": narrator_status,
        "narrator": narrator,
        "total_segments": total,
        "dialogue_count": dialogue_count,
        "chunks": chunks,
        "judge_dir": str(judge_dir),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
