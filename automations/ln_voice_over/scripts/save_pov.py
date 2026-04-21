"""Write a detected POV character back to chapters/manifest.json.

Scoped to a single chapter entry; other entries untouched.

Usage:
    python -m automations.ln_voice_over.scripts.save_pov <manifest_path> <chapter_number> <pov_value>

Where <pov_value> is a character name, or the literal string "null" for
third-person chapters with no first-person narrator.
"""

import json
import sys
from pathlib import Path


def main():
    manifest_path = Path(sys.argv[1])
    chapter_raw = sys.argv[2]
    pov_value = sys.argv[3]

    parsed = None if pov_value.strip().lower() in ("null", "none", "") else pov_value.strip()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next((e for e in manifest if str(e["number"]) == chapter_raw), None)
    if entry is None:
        print(f"ERROR: Chapter '{chapter_raw}' not in manifest", file=sys.stderr)
        sys.exit(1)

    entry["pov_character"] = parsed
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Saved pov_character={parsed!r} for chapter {chapter_raw} in {manifest_path}")


if __name__ == "__main__":
    main()
