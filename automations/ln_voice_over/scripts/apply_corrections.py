"""Write the reviewed chapter by applying judge corrections to the parsed base.

Merges three sources:
  1. The parsed chapter (structure: segments, types, text).
  2. The original Sonnet attribution under `extracted/chapter_<id>/`.
  3. Judge corrections — a JSON array of `{index, speaker}` entries.

For each dialogue segment, speaker = correction override if present, else
the original Sonnet attribution (canonicalised), else None. The result is
saved as a Chapter to `reviewed/chapter_<id>.json` with `reviewed=True`.
A sidecar `reviewed/chapter_<id>_report.json` lists every correction
with before/after so the change is auditable.

Usage:
    python -m ...apply_corrections <slug> <chapter_id> '<corrections_json>'

`<corrections_json>` is a JSON array. An empty array [] means all
existing judge-confirmed attributions are accepted as-is.
"""

import json
import sys
from pathlib import Path

from automations.ln_voice_over.models import Chapter, CharacterRegistry
from automations.ln_voice_over.project import load_characters
from automations.ln_voice_over.split import normalize_chapter_arg

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"


def _canonicalise(raw: str, registry: CharacterRegistry) -> str:
    if raw in ("Narrator", "Unknown", "I"):
        return raw
    char = registry.find(raw) or registry.fuzzy_find(raw)
    return char.name if char else raw


def _find_original(extracted_dir: Path) -> Path:
    matches = sorted(extracted_dir.glob("claude-sonnet_skill_*.json"))
    if not matches:
        print(f"ERROR: No claude-sonnet_skill_*.json in {extracted_dir}", file=sys.stderr)
        sys.exit(1)
    return matches[-1]


def main() -> None:
    slug = sys.argv[1]
    chapter_arg = sys.argv[2]
    corrections = json.loads(sys.argv[3])

    padded = normalize_chapter_arg(chapter_arg)
    project_dir = PROJECTS_DIR / slug
    parsed_path = project_dir / "parsed" / f"chapter_{padded}.json"
    extracted_dir = project_dir / "extracted" / f"chapter_{padded}"
    reviewed_path = project_dir / "reviewed" / f"chapter_{padded}.json"
    report_path = project_dir / "reviewed" / f"chapter_{padded}_report.json"

    chapter = Chapter.load(parsed_path)
    original = json.loads(_find_original(extracted_dir).read_text(encoding="utf-8"))

    series_slug = slug.rsplit("/", 1)[0] if "/" in slug else slug
    registry = load_characters(series_slug)

    overrides: dict[int, str] = {}
    for corr in corrections:
        overrides[int(corr["index"])] = corr["speaker"]

    new_segments = []
    changes: list[dict] = []
    for seg in chapter.segments:
        key = str(seg.index)
        raw_orig = original.get(key)
        canonical_orig = _canonicalise(raw_orig, registry) if raw_orig else None
        if seg.index in overrides:
            new_speaker: str | None = overrides[seg.index]
            if new_speaker != canonical_orig:
                changes.append(
                    {
                        "index": seg.index,
                        "old": canonical_orig,
                        "new": new_speaker,
                    }
                )
        else:
            new_speaker = canonical_orig

        new_segments.append(seg.model_copy(update={"speaker": new_speaker}))

    reviewed = chapter.model_copy(update={"segments": tuple(new_segments), "reviewed": True})
    reviewed.save(reviewed_path)

    report = {
        "save_path": str(reviewed_path),
        "total_segments": len(new_segments),
        "total_corrections": len(changes),
        "changes": changes,
    }
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
