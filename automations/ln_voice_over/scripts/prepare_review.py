"""Prepare review data for speaker attribution divergences.

Loads an attributed chapter and its flags, extracts context windows
around each divergence, and prints a JSON blob to stdout for the
review skill to analyze.

Usage:
    python prepare_review.py <slug> <chapter_id> [--context N]
"""

import argparse
import json
import sys
from pathlib import Path

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"


def format_segment(seg: dict, max_text: int = 200) -> str:
    """Format a segment as a compact string for context display."""
    stype = seg["segment_type"]
    speaker = seg.get("speaker") or ""
    text = seg["text"][:max_text]
    if speaker:
        return f'[{seg["index"]}] ({stype}) {speaker}: "{text}"'
    return f'[{seg["index"]}] ({stype}): "{text}"'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("slug")
    parser.add_argument("chapter_id")
    parser.add_argument(
        "--context", type=int, default=8, help="Segments before/after each divergence"
    )
    args = parser.parse_args()

    project_dir = PROJECTS_DIR / args.slug
    attributed_path = project_dir / "attributed" / f"chapter_{args.chapter_id}.json"
    flags_path = project_dir / "attributed" / f"chapter_{args.chapter_id}_flags.json"

    if not attributed_path.exists():
        print(f"ERROR: Attributed chapter not found: {attributed_path}", file=sys.stderr)
        sys.exit(1)

    chapter = json.loads(attributed_path.read_text(encoding="utf-8"))
    segments = chapter["segments"]
    seg_by_index = {s["index"]: (i, s) for i, s in enumerate(segments)}

    # Load flags (may not exist if chapter has no flags)
    flags = []
    if flags_path.exists():
        flags = json.loads(flags_path.read_text(encoding="utf-8"))

    divergences = [f for f in flags if f.get("type") == "divergence"]

    # Build context for each divergence
    review_items = []
    for flag in divergences:
        idx = int(flag["index"])
        pos_tuple = seg_by_index.get(idx)
        if pos_tuple is None:
            continue
        pos, seg = pos_tuple

        start = max(0, pos - args.context)
        end = min(len(segments), pos + args.context + 1)

        context_before = [format_segment(segments[i]) for i in range(start, pos)]
        context_after = [format_segment(segments[i]) for i in range(pos + 1, end)]

        review_items.append(
            {
                "index": idx,
                "current_speaker": seg.get("speaker"),
                "sources": flag.get("sources", {}),
                "segment_text": seg["text"],
                "context_before": context_before,
                "context_after": context_after,
            }
        )

    output_dir = project_dir / "reviewed"
    result = {
        "slug": args.slug,
        "chapter_id": args.chapter_id,
        "chapter_title": chapter.get("title", ""),
        "pov_character": chapter.get("pov_character", ""),
        "total_segments": len(segments),
        "context_window": args.context,
        "divergence_count": len(review_items),
        "divergences": review_items,
        "output_path": str(output_dir / f"chapter_{args.chapter_id}.json"),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
