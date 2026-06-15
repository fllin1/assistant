"""Config helper tests for the dialogue stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from automations.ln_voice_over_v2.stages.dialogue.config import load_character_registry


def test_load_character_registry_reads_valid_characters_json(tmp_path: Path) -> None:
    """A valid characters config loads as a character registry."""
    registry_path = tmp_path / "characters.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "characters": [
                    {
                        "name": "Horikita Suzune",
                        "aliases": ["Horikita"],
                        "role": "main",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    registry = load_character_registry(registry_path)

    assert registry.resolve("Horikita") == "Horikita Suzune"


def test_load_character_registry_missing_file_raises(tmp_path: Path) -> None:
    """A missing characters config raises before any fallback policy can apply."""
    with pytest.raises(FileNotFoundError):
        load_character_registry(tmp_path / "missing-characters.json")
