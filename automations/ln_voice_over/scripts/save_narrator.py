"""Write a detected narrator back to chapters/manifest.json.

Scoped to a single chapter entry; other entries untouched.

Usage:
    python -m automations.ln_voice_over.scripts.save_narrator \
        <manifest_path> <chapter_number> <narrator_value>

Where <narrator_value> is a character name, or the literal string "null" for
detected third-person chapters with the omniscient narrator.
"""

import json
import sys
from pathlib import Path

from automations.ln_voice_over.split import chapter_id, normalize_chapter_arg


def main() -> None:
    manifest_path = Path(sys.argv[1])
    chapter_raw = sys.argv[2]
    narrator_value = sys.argv[3]

    normalized = narrator_value.strip()
    narrator = None if normalized.lower() in ("null", "none", "") else normalized

    padded = normalize_chapter_arg(chapter_raw)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next((e for e in manifest if chapter_id(e) == padded), None)
    if entry is None:
        print(f"ERROR: Chapter '{chapter_raw}' not in manifest", file=sys.stderr)
        sys.exit(1)

    entry["narrator_status"] = "detected"
    entry["narrator"] = narrator
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Saved narrator={narrator!r} for chapter {chapter_raw} in {manifest_path}")


if __name__ == "__main__":
    main()
