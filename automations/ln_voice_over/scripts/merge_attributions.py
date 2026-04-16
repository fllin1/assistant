"""Merge chunk attribution outputs into a single result file.

Reads agent output JSONs, resolves overlaps (preferring chunks where
segments have more surrounding context), normalizes "I" to the POV
character, and saves the final attribution.

Usage:
    python -m automations.ln_voice_over.scripts.merge_attributions <metadata_json>

Where metadata_json is the JSON string output by prepare_chunks.py.
"""

import json
import shutil
import sys
from collections import Counter
from datetime import date
from pathlib import Path

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"


def main():
    metadata = json.loads(sys.argv[1])

    slug = metadata["slug"]
    chapter_file_id = metadata["chapter_file_id"]
    pov_character = metadata["pov_character"]
    dialogue_count = metadata["dialogue_count"]
    chunks = metadata["chunks"]
    tmp_dir = Path(metadata["tmp_dir"])

    merged = {}

    for i, chunk in enumerate(chunks):
        output_path = Path(chunk["output_path"])
        if not output_path.exists():
            print(f"WARNING: Missing output for chunk {chunk['chunk_idx']}", file=sys.stderr)
            continue

        with open(output_path) as f:
            content = f.read().strip()
            # Handle case where agent wraps JSON in markdown code blocks
            if content.startswith("```"):
                lines = content.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                content = "\n".join(lines)
            attributions = json.loads(content)

        start_idx = chunk["start_index"]
        end_idx = chunk["end_index"]

        for idx_str, speaker in attributions.items():
            idx = int(idx_str)
            # For overlap regions, prefer the chunk where segment is not at the edge
            # i.e., keep the attribution from the earlier chunk for overlap zones
            if idx_str in merged:
                continue  # earlier chunk already set it (has more leading context)
            merged[idx_str] = speaker

    # Normalize "I" to POV character
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

    with open(out_path, "w") as f:
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
