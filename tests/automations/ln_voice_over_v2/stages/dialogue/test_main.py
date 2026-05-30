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


def test_cli_passes_timeout_to_config(monkeypatch):
    captured = {}

    def fake_run_dialogue(config):
        captured["config"] = config
        return SimpleNamespace(dialogue_path=Path("/tmp/x/dialogue/chapter_01.json"))

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.__main__.run_dialogue",
        fake_run_dialogue,
    )

    main(["--series", "s", "--volume", "v1", "--chapter", "chapter_01", "--timeout", "42"])
    assert captured["config"].timeout_seconds == 42

    main(["--series", "s", "--volume", "v1", "--chapter", "chapter_01"])
    assert captured["config"].timeout_seconds == 600


def test_cli_volume_passes_timeout_to_config(monkeypatch):
    captured = {}

    class _VolumeResult:
        outcomes = ()
        written = 0
        skipped = 0
        failed = 0

    def fake_run_volume(config):
        captured["config"] = config
        return _VolumeResult()

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.__main__.run_dialogue_volume",
        fake_run_volume,
    )

    result = main(["--series", "s", "--volume", "v1", "--timeout", "77"])

    assert result == 0
    assert captured["config"].timeout_seconds == 77


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


def test_cli_runs_whole_volume_when_chapter_omitted(monkeypatch, capsys):
    class _Inner:
        skipped = False
        dialogue_path = Path("/tmp/x/dialogue/chapter_01.json")

    class _Outcome:
        chapter_id = "chapter_01"
        error = None
        result = _Inner()

    class _VolumeResult:
        outcomes = (_Outcome(),)
        written = 1
        skipped = 0
        failed = 0

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.__main__.run_dialogue_volume",
        lambda config: _VolumeResult(),
    )

    result = main(["--series", "series-a", "--volume", "v1"])

    captured = capsys.readouterr()
    assert result == 0
    assert "chapter_01.json" in captured.out
    assert "1 written" in captured.out


def test_cli_volume_returns_1_when_a_chapter_fails(monkeypatch, capsys):
    class _Outcome:
        chapter_id = "chapter_02"
        error = "boom"
        result = None

    class _VolumeResult:
        outcomes = (_Outcome(),)
        written = 0
        skipped = 0
        failed = 1

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.dialogue.__main__.run_dialogue_volume",
        lambda config: _VolumeResult(),
    )

    result = main(["--series", "series-a", "--volume", "v1"])

    assert result == 1
    assert "boom" in capsys.readouterr().err
