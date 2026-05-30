"""Prompt contract tests for dialogue attribution."""

from __future__ import annotations

from automations.ln_voice_over_v2.stages.dialogue.prompts import DIALOGUE_PROMPT


def test_dialogue_prompt_excludes_context_and_narration_from_decisions() -> None:
    """The prompt forbids decisions for non-owned background segment roles."""
    assert '"context"' in DIALOGUE_PROMPT
    assert '"narration"' in DIALOGUE_PROMPT
    assert "never emit a decision for them" in DIALOGUE_PROMPT


def test_dialogue_prompt_uses_narrator_hint_as_default_narrator() -> None:
    """The prompt tells the model how to use narrator_hint without inventing names."""
    assert "narrator_hint" in DIALOGUE_PROMPT
    assert "default narrator" in DIALOGUE_PROMPT
    assert "explicit in-chapter evidence overrides" in DIALOGUE_PROMPT
