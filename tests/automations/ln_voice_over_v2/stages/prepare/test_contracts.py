"""Contract-level tests for prepare-stage models."""

from __future__ import annotations

import json

import pytest
from automations.ln_voice_over_v2.stages.prepare.contracts import PreparedTextUnit
from pydantic import ValidationError


def test_prepared_text_unit_defaults_needs_review_false() -> None:
    """Older payloads without the additive field parse with the safe default."""
    payload = (
        '{"text_unit_id": "unit_000000", "order": 0, "text": "x", '
        '"source_path": "source/pages/001.png", "source_locator": {}}'
    )

    unit = PreparedTextUnit.model_validate_json(payload)

    assert unit.needs_review is False


def test_prepared_text_unit_round_trips_needs_review_true() -> None:
    """The review flag is part of the model and survives JSON serialization."""
    payload = (
        '{"text_unit_id": "unit_000000", "order": 0, "text": "", '
        '"source_path": "source/pages/001.png", "source_locator": {"page": 1}, '
        '"needs_review": true}'
    )

    unit = PreparedTextUnit.model_validate_json(payload)

    assert unit.needs_review is True
    assert json.loads(unit.model_dump_json())["needs_review"] is True


def test_prepared_text_unit_rejects_unknown_key() -> None:
    """The additive field does not weaken `extra="forbid"` typo protection."""
    payload = (
        '{"text_unit_id": "unit_000000", "order": 0, "text": "x", '
        '"source_path": "source/pages/001.png", "source_locator": {}, '
        '"needs_reveiw": true}'
    )

    with pytest.raises(ValidationError):
        PreparedTextUnit.model_validate_json(payload)
