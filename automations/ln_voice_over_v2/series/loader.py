"""Series-level config loaders for LNVO v2."""

from __future__ import annotations

from pathlib import Path

from ..common.json_io import load_json_contract
from .contracts import CharacterRegistry


def load_character_registry(path: Path) -> CharacterRegistry:
    """Load a `CharacterRegistry` from disk using the strict JSON contract loader.

    Args:
        path: Path to a `characters.json` file.

    Returns:
        Parsed character registry.
    """
    return load_json_contract(path, CharacterRegistry)
