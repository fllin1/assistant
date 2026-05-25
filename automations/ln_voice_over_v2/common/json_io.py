"""JSON round-trip helpers for strict contract models."""

from __future__ import annotations

import tempfile
from pathlib import Path

from pydantic import BaseModel


def load_json_contract[ModelT: BaseModel](path: Path, model_type: type[ModelT]) -> ModelT:
    """Load a JSON contract from disk."""
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def save_json_contract(path: Path, model: BaseModel) -> None:
    """Save a JSON contract atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, suffix=".tmp", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(model.model_dump_json(indent=2))
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
