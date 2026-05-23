"""Migrate old pov_character fields to narrator fields.

This is a one-time data migration for existing local project artifacts. It
updates the active manifest plus parsed/reviewed chapter JSON files for a
single `<series>/<volume>` slug.

Usage:
    python -m automations.ln_voice_over.scripts.migrate_narrator_fields \
        <series>/<volume> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"


def _target_fields(old_value: Any) -> tuple[str, str | None]:
    if old_value is None:
        return "unset", None
    if not isinstance(old_value, str):
        raise ValueError(f"Expected pov_character to be string or null, got {old_value!r}")
    return "detected", old_value


def _migrate_object(data: dict[str, Any], path: Path) -> tuple[bool, str]:
    has_old = "pov_character" in data
    has_status = "narrator_status" in data
    has_narrator = "narrator" in data

    if has_old:
        status, narrator = _target_fields(data["pov_character"])
        if has_status and data["narrator_status"] != status:
            raise ValueError(
                f"{path}: conflicting narrator_status {data['narrator_status']!r} "
                f"for pov_character {data['pov_character']!r}"
            )
        if has_narrator and data["narrator"] != narrator:
            raise ValueError(
                f"{path}: conflicting narrator {data['narrator']!r} "
                f"for pov_character {data['pov_character']!r}"
            )
        data["narrator_status"] = status
        data["narrator"] = narrator
        del data["pov_character"]
        return True, status

    if has_status and has_narrator:
        return False, "already_migrated"

    raise ValueError(f"{path}: missing both old and new narrator fields")


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _migrate_manifest(path: Path, dry_run: bool) -> dict[str, int]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    stats: dict[str, int] = {}
    changed = False
    for row in data:
        did_change, status = _migrate_object(row, path)
        stats[status] = stats.get(status, 0) + 1
        changed = changed or did_change
    if changed and not dry_run:
        _write_json(path, data)
    return stats


def _chapter_paths(project_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for dirname in ("parsed", "reviewed"):
        root = project_dir / dirname
        if not root.exists():
            continue
        paths.extend(p for p in sorted(root.glob("chapter_*.json")) if "_report" not in p.name)
    return paths


def _migrate_chapters(project_dir: Path, dry_run: bool) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for path in _chapter_paths(project_dir):
        data = json.loads(path.read_text(encoding="utf-8"))
        did_change, status = _migrate_object(data, path)
        stage = path.parent.name
        stage_stats = stats.setdefault(stage, {})
        stage_stats[status] = stage_stats.get(status, 0) + 1
        if did_change and not dry_run:
            _write_json(path, data)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("slug", help="<series>/<volume>")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    args = parser.parse_args()

    project_dir = PROJECTS_DIR / args.slug
    if not project_dir.exists():
        print(f"ERROR: No project directory for {args.slug}: {project_dir}", file=sys.stderr)
        sys.exit(1)

    try:
        report = {
            "slug": args.slug,
            "dry_run": args.dry_run,
            "manifest": _migrate_manifest(
                project_dir / "chapters" / "manifest.json", args.dry_run
            ),
            "chapters": _migrate_chapters(project_dir, args.dry_run),
        }
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
