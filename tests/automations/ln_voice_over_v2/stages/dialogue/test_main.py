"""CLI tests for the dialogue stage."""

from pathlib import Path
from types import SimpleNamespace

from automations.ln_voice_over_v2.common.errors import (
    ContractValidationError,
    ValidationProblem,
)
from automations.ln_voice_over_v2.stages.dialogue.__main__ import main


def test_cli_success(monkeypatch, capsys):
    expected_path = Path("/tmp/x/dialogue/chapter_01.json")

    def fake_run_dialogue(config):
        return SimpleNamespace(dialogue_path=expected_path)

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.__main__.run_dialogue",
        fake_run_dialogue,
    )

    result = main(["--series", "series-a", "--volume", "v1", "--chapter", "chapter_01"])

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out == f"{expected_path}\n"


def test_cli_contract_error_exit_2(monkeypatch, capsys):
    def fake_run_dialogue(config):
        raise ContractValidationError(
            [
                ValidationProblem(
                    code="unknown_chapter",
                    message="m",
                    path="chapter_id",
                )
            ]
        )

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.__main__.run_dialogue",
        fake_run_dialogue,
    )

    result = main(["--series", "series-a", "--volume", "v1", "--chapter", "chapter_01"])

    captured = capsys.readouterr()
    assert result == 2
    assert "unknown_chapter" in captured.err


def test_cli_generic_error_exit_1(monkeypatch, capsys):
    def fake_run_dialogue(config):
        raise FileNotFoundError("missing characters.json")

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.__main__.run_dialogue",
        fake_run_dialogue,
    )

    result = main(["--series", "series-a", "--volume", "v1", "--chapter", "chapter_01"])

    captured = capsys.readouterr()
    assert result == 1
    assert "missing characters.json" in captured.err
