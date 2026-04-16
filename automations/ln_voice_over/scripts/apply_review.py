"""Apply review corrections and save the reviewed chapter.

Takes an attributed chapter, applies speaker corrections from the review
skill, marks the chapter as reviewed, and saves to reviewed/.

Usage:
    python -m automations.ln_voice_over.scripts.apply_review \
        <slug> <chapter_id> '<corrections_json>'

Where corrections_json is a JSON array:
    [{"index": 100, "new_speaker": "Horikita Suzune", "reason": "..."}]

An empty array [] means all attributions are confirmed correct.
"""

import json
import sys
from pathlib import Path

from automations.ln_voice_over.models import Chapter

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"


def main() -> None:
    slug = sys.argv[1]
    chapter_id = sys.argv[2]
    corrections = json.loads(sys.argv[3])

    project_dir = PROJECTS_DIR / slug
    attributed_path = project_dir / "attributed" / f"chapter_{chapter_id}.json"
    output_path = project_dir / "reviewed" / f"chapter_{chapter_id}.json"

    chapter = Chapter.load(attributed_path)

    # Build index lookup
    seg_by_index = {s.index: i for i, s in enumerate(chapter.segments)}

    changes = []
    new_segments = list(chapter.segments)
    for corr in corrections:
        idx = int(corr["index"])
        pos = seg_by_index.get(idx)
        if pos is None:
            changes.append({"index": idx, "error": "segment not found"})
            continue
        old_speaker = new_segments[pos].speaker
        new_segments[pos] = new_segments[pos].model_copy(update={"speaker": corr["new_speaker"]})
        changes.append(
            {
                "index": idx,
                "old": old_speaker,
                "new": corr["new_speaker"],
                "reason": corr.get("reason", ""),
            }
        )

    chapter = chapter.model_copy(update={"segments": tuple(new_segments), "reviewed": True})
    chapter.save(output_path)

    report = {
        "save_path": str(output_path),
        "total_corrections": len(changes),
        "changes": changes,
    }
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
