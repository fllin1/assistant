"""Merge chunk attribution outputs into a single result file.

Resolves overlaps (preferring chunks where segments have more surrounding
context), normalizes "I" to the POV character, and saves the final
attribution.

Attributions can be supplied two ways:
  - inline via ``--results '<json>'`` (orchestrator passes sub-agent replies
    directly, avoiding temp-file writes)
  - from files at each chunk's ``output_path`` (legacy path; kept for
    backward compatibility)

Usage:
    python -m automations.ln_voice_over.scripts.merge_attributions <metadata_json>
    python -m ...merge_attributions <metadata_json> --results '<results_json>'

Where ``metadata_json`` is the JSON string output by prepare_chunks.py and
``results_json`` maps chunk_idx (string) to the per-chunk attribution dict.
"""

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import date
from pathlib import Path

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"


def _parse_attribution_text(content: str) -> dict:
    """Strip optional markdown code-fence wrapping and parse attribution JSON."""
    content = content.strip()
    if content.startswith("```"):
        lines = [line for line in content.split("\n") if not line.startswith("```")]
        content = "\n".join(lines)
    return json.loads(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("metadata", help="Metadata JSON from prepare_chunks.py")
    parser.add_argument(
        "--results",
        help="Inline JSON map {chunk_idx: attribution_dict}; skips file reads when provided",
    )
    args = parser.parse_args()

    metadata = json.loads(args.metadata)
    inline_results = json.loads(args.results) if args.results else None

    slug = metadata["slug"]
    chapter_file_id = metadata["chapter_file_id"]
    pov_character = metadata["pov_character"]
    dialogue_count = metadata["dialogue_count"]
    chunks = metadata["chunks"]
    tmp_dir = Path(metadata["tmp_dir"])

    merged = {}

    for chunk in chunks:
        chunk_key = str(chunk["chunk_idx"])
        if inline_results is not None:
            if chunk_key not in inline_results:
                print(f"WARNING: Missing inline result for chunk {chunk_key}", file=sys.stderr)
                continue
            raw = inline_results[chunk_key]
            attributions = raw if isinstance(raw, dict) else _parse_attribution_text(raw)
        else:
            output_path = Path(chunk["output_path"])
            if not output_path.exists():
                print(f"WARNING: Missing output for chunk {chunk['chunk_idx']}", file=sys.stderr)
                continue
            attributions = _parse_attribution_text(output_path.read_text())

        for idx_str, speaker in attributions.items():
            idx = int(idx_str)
            # For overlap regions, prefer the chunk where segment is not at the edge
            # i.e., keep the attribution from the earlier chunk for overlap zones
            if idx_str in merged:
                continue  # earlier chunk already set it (has more leading context)
            merged[idx_str] = speaker

    # Normalize "I" to POV character (skipped for third-person chapters where POV is null)
    if pov_character:
        for idx in merged:
            if merged[idx] == "I":
                merged[idx] = pov_character

    # Sort by index
    sorted_merged = dict(sorted(merged.items(), key=lambda x: int(x[0])))

    # Stats
    total_attributed = len(sorted_merged)
    unknown_count = sum(1 for v in sorted_merged.values() if v == "Unknown")
    narrator_count = sum(1 for v in sorted_merged.values() if v == "Narrator")

    counts = Counter(sorted_merged.values())

    # Save
    out_dir = PROJECTS_DIR / slug / "extracted" / f"chapter_{chapter_file_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    out_path = out_dir / f"claude-sonnet_skill_{today}.json"

    with out_path.open("w") as f:
        json.dump(sorted_merged, f, indent=2)

    # Clean up temp files
    shutil.rmtree(tmp_dir, ignore_errors=True)

    # Report
    report = {
        "save_path": str(out_path),
        "total_dialogue": dialogue_count,
        "total_attributed": total_attributed,
        "unknown": unknown_count,
        "narrator": narrator_count,
        "speakers": dict(counts.most_common()),
    }
    print(json.dumps(report))


if __name__ == "__main__":
    main()
