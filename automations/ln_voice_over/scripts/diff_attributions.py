"""Diff the original Sonnet attribution against the judge pass.

Reads both attribution maps for a chapter, compares speaker per index,
and emits a flag list — one entry per disagreement — with the dialogue's
segment text and near-context for downstream Opus resolution.

The comparison canonicalises the ORIGINAL attribution on the fly (the
judge merge already canonicalises) so naming variants like "Horikita" vs
"Horikita Suzune" don't register as false disagreements.

Output: `judge/chapter_<id>/flags.json`. Stdout prints JSON containing
the flag list plus summary counts.

Usage:
    python -m automations.ln_voice_over.scripts.diff_attributions \\
        <slug> <chapter_id> [--context N]
"""

import argparse
import json
import sys
from pathlib import Path

from automations.ln_voice_over.models import Chapter, CharacterRegistry, Segment, SegmentType
from automations.ln_voice_over.project import load_characters
from automations.ln_voice_over.split import normalize_chapter_arg

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"


def _canonicalise(raw: str, registry: CharacterRegistry) -> str:
    if raw in ("Narrator", "Unknown", "I"):
        return raw
    char = registry.find(raw) or registry.fuzzy_find(raw)
    return char.name if char else raw


def _format_segment(seg: Segment, max_text: int = 200) -> str:
    stype = seg.segment_type.value
    speaker = seg.speaker or ""
    text = seg.text[:max_text]
    if speaker:
        return f'[{seg.index}] ({stype}) {speaker}: "{text}"'
    return f'[{seg.index}] ({stype}): "{text}"'


def _find_original(extracted_dir: Path) -> Path:
    matches = sorted(extracted_dir.glob("claude-sonnet_skill_*.json"))
    if not matches:
        print(f"ERROR: No claude-sonnet_skill_*.json in {extracted_dir}", file=sys.stderr)
        sys.exit(1)
    return matches[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("slug")
    parser.add_argument("chapter_id")
    parser.add_argument("--context", type=int, default=8, help="Segments before/after each flag")
    args = parser.parse_args()

    padded = normalize_chapter_arg(args.chapter_id)
    project_dir = PROJECTS_DIR / args.slug

    extracted_dir = project_dir / "extracted" / f"chapter_{padded}"
    judge_dir = project_dir / "judge" / f"chapter_{padded}"
    parsed_path = project_dir / "parsed" / f"chapter_{padded}.json"

    original_path = _find_original(extracted_dir)
    judge_path = judge_dir / "merged.json"
    if not judge_path.exists():
        print(f"ERROR: Judge merged output missing: {judge_path}", file=sys.stderr)
        sys.exit(1)

    original = json.loads(original_path.read_text(encoding="utf-8"))
    judge = json.loads(judge_path.read_text(encoding="utf-8"))

    series_slug = args.slug.rsplit("/", 1)[0] if "/" in args.slug else args.slug
    registry = load_characters(series_slug)

    chapter = Chapter.load(parsed_path)
    seg_by_index = {s.index: i for i, s in enumerate(chapter.segments)}

    flags: list[dict] = []
    keys = sorted(set(original.keys()) | set(judge.keys()), key=int)
    for key in keys:
        orig_raw = original.get(key)
        judge_speaker = judge.get(key)
        if orig_raw is None or judge_speaker is None:
            continue  # one side missing — covered by missing/unknown flags elsewhere
        orig_canonical = _canonicalise(orig_raw, registry)
        if orig_canonical == judge_speaker:
            continue

        idx = int(key)
        pos = seg_by_index.get(idx)
        if pos is None:
            continue
        seg = chapter.segments[pos]
        if seg.segment_type != SegmentType.DIALOGUE:
            continue

        start = max(0, pos - args.context)
        end = min(len(chapter.segments), pos + args.context + 1)
        flags.append(
            {
                "index": idx,
                "segment_text": seg.text,
                "original_speaker": orig_canonical,
                "judge_speaker": judge_speaker,
                "context_before": [
                    _format_segment(chapter.segments[i]) for i in range(start, pos)
                ],
                "context_after": [
                    _format_segment(chapter.segments[i]) for i in range(pos + 1, end)
                ],
            }
        )

    flags_path = judge_dir / "flags.json"
    flags_path.write_text(json.dumps(flags, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report = {
        "slug": args.slug,
        "chapter_id": padded,
        "chapter_title": chapter.title,
        "pov_character": chapter.pov_character,
        "total_original": len(original),
        "total_judge": len(judge),
        "flag_count": len(flags),
        "flags_path": str(flags_path),
        "flags": flags,
    }
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
