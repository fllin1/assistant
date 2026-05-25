"""Tests for the prepare-stage Codex OCR boundary."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from automations.ln_voice_over_v2.common.errors import ContractValidationError
from automations.ln_voice_over_v2.stages.prepare.ocr import (
    OcrPageResult,
    load_cached_ocr,
    run_codex_ocr,
    save_ocr,
)
from pydantic import ValidationError


def test_run_codex_ocr_builds_exact_argv_and_parses_stdout(tmp_path: Path) -> None:
    """The OCR helper passes the locked argv shape to `codex exec`."""
    image = tmp_path / "001.png"
    image.write_bytes(b"png")
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout='{"transcript":"Hello","is_illustration":false}',
        stderr="progress",
    )

    with patch(
        "automations.ln_voice_over_v2.stages.prepare.ocr.subprocess.run",
        return_value=completed,
    ) as run:
        result = run_codex_ocr(
            image,
            model="model-a",
            executable="codex-test",
            timeout_seconds=12,
            prompt="prompt text",
        )

    assert result == OcrPageResult(transcript="Hello", is_illustration=False)
    run.assert_called_once_with(
        [
            "codex-test",
            "exec",
            "-i",
            str(image),
            "-m",
            "model-a",
            "--ephemeral",
            "--skip-git-repo-check",
            "-s",
            "read-only",
            "prompt text",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=12,
        check=True,
    )


@pytest.mark.parametrize(
    "stdout",
    [
        '```json\n{"transcript":"x","is_illustration":false}\n```',
        '{"transcript":"x","is_illustration":false}\nOK done',
    ],
)
def test_run_codex_ocr_rejects_non_raw_json(stdout: str, tmp_path: Path) -> None:
    """Fenced JSON and trailing prose are malformed OCR output."""
    image = tmp_path / "001.png"
    image.write_bytes(b"png")
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=stdout, stderr="stderr details"
    )

    with (
        pytest.raises(ContractValidationError) as exc_info,
        patch(
            "automations.ln_voice_over_v2.stages.prepare.ocr.subprocess.run",
            return_value=completed,
        ),
    ):
        run_codex_ocr(image)

    assert [problem.code for problem in exc_info.value.problems] == ["ocr_malformed"]
    assert "stderr details" in exc_info.value.problems[0].message


def test_ocr_page_result_rejects_extra_keys() -> None:
    """OCR cache rows are strict and reject unplanned fields."""
    with pytest.raises(ValidationError):
        OcrPageResult.model_validate({"transcript": "Hello", "is_illustration": False, "extra": 1})


def test_run_codex_ocr_wraps_nonzero_exit(tmp_path: Path) -> None:
    """A non-zero Codex CLI exit becomes a RuntimeError containing stderr."""
    image = tmp_path / "001.png"
    image.write_bytes(b"png")

    with (
        pytest.raises(RuntimeError, match="bad cli"),
        patch(
            "automations.ln_voice_over_v2.stages.prepare.ocr.subprocess.run",
            side_effect=subprocess.CalledProcessError(
                returncode=2, cmd=["codex"], stderr="bad cli"
            ),
        ),
    ):
        run_codex_ocr(image)


def test_load_cached_ocr_missing_malformed_and_valid(tmp_path: Path) -> None:
    """OCR caches return `None` when absent or strict parsing fails."""
    missing = tmp_path / "missing.json"
    assert load_cached_ocr(missing) is None

    for name, payload in {
        "extra.json": '{"transcript":"x","is_illustration":false,"extra":1}',
        "missing-key.json": '{"transcript":"x"}',
        "not-json.json": "not json",
    }.items():
        path = tmp_path / name
        path.write_text(payload, encoding="utf-8")
        assert load_cached_ocr(path) is None

    valid = tmp_path / "valid.json"
    valid.write_text('{"transcript":"x","is_illustration":true}', encoding="utf-8")
    assert load_cached_ocr(valid) == OcrPageResult(transcript="x", is_illustration=True)


def test_save_ocr_writes_atomically(tmp_path: Path) -> None:
    """A failed replace leaves the destination content unchanged."""
    path = tmp_path / "ocr" / "001.json"
    original = '{"transcript":"old","is_illustration":false}'
    path.parent.mkdir()
    path.write_text(original, encoding="utf-8")

    with (
        pytest.raises(RuntimeError, match="replace failed"),
        patch.object(Path, "replace", side_effect=RuntimeError("replace failed")),
    ):
        save_ocr(path, OcrPageResult(transcript="new", is_illustration=True))

    assert path.read_text(encoding="utf-8") == original

    save_ocr(path, OcrPageResult(transcript="new", is_illustration=True))
    assert load_cached_ocr(path) == OcrPageResult(transcript="new", is_illustration=True)
