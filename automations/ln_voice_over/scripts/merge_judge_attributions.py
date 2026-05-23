"""Merge judge-pass chunk attributions, canonicalise names, save merged output.

Accepts the metadata JSON from `prepare_judge_chunks.py` and an inline
`--results '<json>'` map of `{chunk_idx: {index: speaker}}` payloads, one
per sub-agent reply. Merges the same way as `merge_attributions.py`
(earlier chunk wins overlaps) but additionally canonicalises each speaker
name against the series' `CharacterRegistry` — taking over the job the
deleted `lnvo resolve` stage used to do.

Output: `judge/chapter_<id>/merged.json` — flat `{index: speaker}` map
using canonical names where the registry resolved them; "Narrator",
"Unknown" and "I" are left alone, and "I" is normalised to the chapter
narrator afterwards if one is set.

Usage:
    python -m ...merge_judge_attributions '<metadata_json>' --results '<results_json>'
"""

import argparse
import json
import sys
from pathlib import Path

from automations.ln_voice_over.models import CharacterRegistry
from automations.ln_voice_over.project import load_characters

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"


def _parse_attribution_text(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        lines = [line for line in content.split("\n") if not line.startswith("```")]
        content = "\n".join(lines)
    return json.loads(content)


def _canonicalise(raw: str, registry: CharacterRegistry) -> str:
    if raw in ("Narrator", "Unknown", "I"):
        return raw
    char = registry.find(raw) or registry.fuzzy_find(raw)
    return char.name if char else raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("metadata", help="JSON from prepare_judge_chunks.py")
    parser.add_argument("--results", required=True, help="{chunk_idx: attribution_dict}")
    args = parser.parse_args()

    metadata = json.loads(args.metadata)
    inline_results = json.loads(args.results)

    slug = metadata["slug"]
    judge_dir = Path(metadata["judge_dir"])
    narrator = metadata["narrator"]
    chunks = metadata["chunks"]

    # Series slug = everything before the last "/" in the project slug.
    series_slug = slug.rsplit("/", 1)[0] if "/" in slug else slug
    registry = load_characters(series_slug)

    merged: dict[str, str] = {}
    for chunk in chunks:
        key = str(chunk["chunk_idx"])
        if key not in inline_results:
            print(f"WARNING: Missing judge result for chunk {key}", file=sys.stderr)
            continue
        raw = inline_results[key]
        attrs = raw if isinstance(raw, dict) else _parse_attribution_text(raw)
        for idx_str, speaker in attrs.items():
            if idx_str in merged:
                continue  # earlier chunk already set it (has more leading context)
            merged[idx_str] = _canonicalise(speaker, registry)

    if narrator:
        for idx in merged:
            if merged[idx] == "I":
                merged[idx] = narrator

    sorted_merged = dict(sorted(merged.items(), key=lambda x: int(x[0])))

    out_path = judge_dir / "merged.json"
    out_path.write_text(json.dumps(sorted_merged, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps({"save_path": str(out_path), "total_attributed": len(sorted_merged)}))


if __name__ == "__main__":
    main()
