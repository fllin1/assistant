"""Tests for the one-time narrator-field data migration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from automations.ln_voice_over.scripts import migrate_narrator_fields


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_migrate_narrator_fields_dry_run_leaves_files_unchanged(
    tmp_path: Path,
    monkeypatch,
):
    project_dir = tmp_path / "series" / "v1"
    manifest_path = project_dir / "chapters" / "manifest.json"
    parsed_path = project_dir / "parsed" / "chapter_01.json"
    _write_json(
        manifest_path,
        [
            {"number": 1, "title": "One", "file": "chapter_01.txt", "pov_character": "Alice"},
            {"number": 2, "title": "Two", "file": "chapter_02.txt", "pov_character": None},
        ],
    )
    _write_json(
        parsed_path,
        {
            "chapter_number": 1,
            "title": "One",
            "source_file": "chapter_01.txt",
            "pov_character": "Alice",
            "segments": [],
        },
    )
    before_manifest = manifest_path.read_text(encoding="utf-8")
    before_parsed = parsed_path.read_text(encoding="utf-8")

    monkeypatch.setattr(migrate_narrator_fields, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["migrate_narrator_fields.py", "series/v1", "--dry-run"],
    )

    migrate_narrator_fields.main()

    assert manifest_path.read_text(encoding="utf-8") == before_manifest
    assert parsed_path.read_text(encoding="utf-8") == before_parsed


def test_migrate_narrator_fields_writes_new_schema(tmp_path: Path, monkeypatch):
    project_dir = tmp_path / "series" / "v1"
    manifest_path = project_dir / "chapters" / "manifest.json"
    reviewed_path = project_dir / "reviewed" / "chapter_01.json"
    _write_json(
        manifest_path,
        [
            {"number": 1, "title": "One", "file": "chapter_01.txt", "pov_character": "Alice"},
            {"number": 2, "title": "Two", "file": "chapter_02.txt", "pov_character": None},
        ],
    )
    _write_json(
        reviewed_path,
        {
            "chapter_number": 1,
            "title": "One",
            "source_file": "chapter_01.txt",
            "pov_character": "Alice",
            "segments": [],
            "reviewed": True,
        },
    )

    monkeypatch.setattr(migrate_narrator_fields, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["migrate_narrator_fields.py", "series/v1"])

    migrate_narrator_fields.main()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
    assert manifest[0]["narrator_status"] == "detected"
    assert manifest[0]["narrator"] == "Alice"
    assert manifest[1]["narrator_status"] == "unset"
    assert manifest[1]["narrator"] is None
    assert "pov_character" not in manifest[0]
    assert reviewed["narrator_status"] == "detected"
    assert reviewed["narrator"] == "Alice"
    assert "pov_character" not in reviewed
