"""Tests for the dialogue Codex agent and prompt builder."""

import subprocess

import pytest
from automations.ln_voice_over_v2.common.errors import ContractValidationError
from automations.ln_voice_over_v2.stages.dialogue.agent import (
    DialogueProposal,
    run_codex_dialogue,
)
from automations.ln_voice_over_v2.stages.dialogue.context import (
    ChapterPayload,
    PayloadSegment,
)
from automations.ln_voice_over_v2.stages.dialogue.prompts import build_prompt


def test_run_codex_dialogue_uses_text_only_argv(monkeypatch):
    prompt = "classify this"
    expected = (
        '{"decisions":[{"segment_id":"seg_000001","is_dialogue":true,'
        '"speaker_raw":"Ann","speaker_gender":"female","reason":"spoken"}],'
        '"narrator_raw":null,'
        '"review_notes":[]}'
    )

    def fake_run(argv, **kwargs):
        assert argv == [
            "codex-bin",
            "exec",
            "-m",
            "test-model",
            "--ephemeral",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "-s",
            "read-only",
            prompt,
        ]
        assert "-i" not in argv
        assert kwargs == {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "timeout": 12,
            "check": True,
        }
        return subprocess.CompletedProcess(argv, 0, stdout=expected, stderr="")

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.agent.subprocess.run",
        fake_run,
    )

    proposal = run_codex_dialogue(
        prompt,
        model="test-model",
        executable="codex-bin",
        timeout_seconds=12,
    )

    assert isinstance(proposal, DialogueProposal)
    assert proposal.decisions[0].segment_id == "seg_000001"
    assert proposal.decisions[0].speaker_raw == "Ann"
    assert proposal.decisions[0].speaker_gender == "female"


def test_run_codex_dialogue_malformed_stdout_raises_contract_error(monkeypatch):
    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.agent.subprocess.run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout="not json", stderr=""),
    )

    with pytest.raises(ContractValidationError) as exc_info:
        run_codex_dialogue("prompt")

    assert [problem.code for problem in exc_info.value.problems] == ["dialogue_malformed"]


def test_run_codex_dialogue_process_failure_raises_runtime_error(monkeypatch):
    def fake_run(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv, stderr="boom")

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.agent.subprocess.run",
        fake_run,
    )

    with pytest.raises(RuntimeError, match="codex dialogue failed: boom") as exc_info:
        run_codex_dialogue("secret-prompt-text")

    # The prompt-bearing CalledProcessError is suppressed from the chain
    # (`from None`), so a printed traceback cannot surface argv via __cause__.cmd.
    err = exc_info.value
    assert "secret-prompt-text" not in str(err)
    assert err.__cause__ is None
    assert err.__suppress_context__ is True


def test_run_codex_dialogue_timeout_raises_clean_runtime_error(monkeypatch):
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.agent.subprocess.run",
        fake_run,
    )

    with pytest.raises(RuntimeError) as exc_info:
        run_codex_dialogue("secret-prompt-text", timeout_seconds=5)

    err = exc_info.value
    assert "timed out after 5s" in str(err)
    # Prompt must not leak: message is clean and the prompt-bearing TimeoutExpired
    # (whose `cmd` is the full argv) is suppressed from the chain (`from None`).
    assert "secret-prompt-text" not in str(err)
    assert err.__cause__ is None
    assert err.__suppress_context__ is True


def test_build_prompt_includes_roster_and_payload_json():
    payload = ChapterPayload(
        series="series-1",
        volume="volume-1",
        chapter_id="chapter_01",
        narrator_hint=None,
        segments=(
            PayloadSegment(
                segment_id="seg_000001",
                text='"Hello."',
                role="candidate",
            ),
        ),
        candidate_ids=("seg_000001",),
    )

    prompt = build_prompt(payload, ("Ann", "Narrator"))

    assert "Ann" in prompt
    assert "Narrator" in prompt
    assert payload.model_dump_json() in prompt
