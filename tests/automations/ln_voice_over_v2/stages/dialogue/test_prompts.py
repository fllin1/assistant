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


def test_dialogue_prompt_requests_gender_for_unregistered_speakers() -> None:
    """The prompt asks for bounded gender fallback metadata."""
    assert "speaker_gender" in DIALOGUE_PROMPT
    assert '"male"' in DIALOGUE_PROMPT
    assert '"female"' in DIALOGUE_PROMPT
    assert '"unknown"' in DIALOGUE_PROMPT
    assert "Infer speaker_gender only from textual evidence" in DIALOGUE_PROMPT
    assert "absent from the" in DIALOGUE_PROMPT
