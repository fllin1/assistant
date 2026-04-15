"""Apply review corrections and save the reviewed chapter.

Takes an attributed chapter, applies speaker corrections from the review
skill, marks the chapter as reviewed, and saves to reviewed/.

Usage:
    python apply_review.py <slug> <chapter_id> '<corrections_json>'

Where corrections_json is a JSON array:
    [{"index": 100, "new_speaker": "Horikita Suzune", "reason": "..."}]

An empty array [] means all attributions are confirmed correct.
"""

import json
import sys
import tempfile
from pathlib import Path

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"


def main() -> None:
    slug = sys.argv[1]
    chapter_id = sys.argv[2]
    corrections = json.loads(sys.argv[3])

    project_dir = PROJECTS_DIR / slug
    attributed_path = project_dir / "attributed" / f"chapter_{chapter_id}.json"
    output_path = project_dir / "reviewed" / f"chapter_{chapter_id}.json"

    chapter = json.loads(attributed_path.read_text(encoding="utf-8"))

    # Build index lookup
    seg_by_index = {s["index"]: s for s in chapter["segments"]}

    changes = []
    for corr in corrections:
        idx = int(corr["index"])
        seg = seg_by_index.get(idx)
        if seg is None:
            changes.append({"index": idx, "error": "segment not found"})
            continue
        old_speaker = seg.get("speaker")
        seg["speaker"] = corr["new_speaker"]
        seg["confidence"] = 1.0
        seg["attribution_method"] = "reviewed"
        changes.append(
            {
                "index": idx,
                "old": old_speaker,
                "new": corr["new_speaker"],
                "reason": corr.get("reason", ""),
            }
        )

    chapter["reviewed"] = True
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write via temp file
    with tempfile.NamedTemporaryFile(
        mode="w", dir=output_path.parent, suffix=".tmp", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(chapter, tmp, indent=2, ensure_ascii=False)
        tmp_path = Path(tmp.name)
    tmp_path.rename(output_path)

    report = {
        "save_path": str(output_path),
        "total_corrections": len(changes),
        "changes": changes,
    }
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
