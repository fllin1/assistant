"""Codex CLI OCR boundary and page-level OCR cache helpers."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from ...common.errors import ContractValidationError, ValidationProblem
from .prompts import OCR_PROMPT

_REFUSAL_PREFIX_RE: re.Pattern[str] = re.compile(
    r"^(?:"
    r"i(?:\s+can(?:not|['’]t)|\s+won['’]t|['’]m\s+sorry|['’]m\s+not\s+able)"
    r"|sorry,?\s+(?:but|i)"
    r"|as\s+an\s+ai"
    r")\b",
    re.IGNORECASE,
)


class OcrPageResult(BaseModel):
    """Strict OCR result for a single rasterized page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transcript: str
    is_illustration: bool


def _looks_like_refusal(transcript: str) -> bool:
    """Return whether a transcript starts with a known OCR refusal prefix.

    Args:
        transcript: OCR transcript text to classify.

    Returns:
        True when the first non-whitespace characters match a known refusal
        family; otherwise false.
    """
    return _REFUSAL_PREFIX_RE.match(transcript.lstrip()[:120]) is not None


def _is_failed_ocr(result: OcrPageResult) -> bool:
    """Classify semantic OCR failures that should be retried or reviewed.

    Args:
        result: Strictly parsed OCR result.

    Returns:
        True for refusal-style transcripts and for the structural empty
        non-illustration sentinel; otherwise false.
    """
    if _looks_like_refusal(result.transcript):
        return True
    return result.transcript == "" and result.is_illustration is False


def run_codex_ocr(
    page_image: Path,
    *,
    model: str = "gpt-5.5",
    executable: str = "codex",
    timeout_seconds: int = 180,
    prompt: str = OCR_PROMPT,
) -> OcrPageResult:
    """Subprocess `codex exec` and parse strict OCR JSON.

    Args:
        page_image: Rasterized page image to pass to the Codex CLI.
        model: Codex model identifier used for OCR.
        executable: Codex CLI executable name or path.
        timeout_seconds: Subprocess timeout in seconds.
        prompt: OCR instruction prompt.

    Returns:
        Parsed OCR result.

    Raises:
        RuntimeError: If the Codex CLI exits non-zero.
        ContractValidationError: If stdout is not strict `OcrPageResult` JSON.
    """
    # --ignore-user-config skips ~/.codex/config.toml so per-user Stop / notify
    # hooks (e.g. oh-my-codex) cannot inject a trailing "task complete" turn that
    # would corrupt the strict-JSON stdout the parser below expects.
    argv = [
        executable,
        "exec",
        "-i",
        str(page_image),
        "-m",
        model,
        "--ephemeral",
        "--skip-git-repo-check",
        "--ignore-user-config",
        "-s",
        "read-only",
        prompt,
    ]
    try:
        completed = subprocess.run(  # noqa: UP022 - plan requires explicit stdout/stderr pipes.
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        raise RuntimeError(f"codex OCR failed for {page_image}: {stderr}") from exc

    try:
        return OcrPageResult.model_validate_json(completed.stdout.strip())
    except ValidationError as parse_err:
        raise ContractValidationError(
            [
                ValidationProblem(
                    code="ocr_malformed",
                    message=f"{parse_err} | stderr={completed.stderr[:500]}",
                    path=str(page_image),
                )
            ]
        ) from parse_err


def load_cached_ocr(path: Path) -> OcrPageResult | None:
    """Return the parsed OCR cache, or `None` when missing or malformed.

    Args:
        path: OCR cache JSON path.

    Returns:
        Parsed OCR result, or `None`.
    """
    if not path.exists():
        return None

    try:
        return OcrPageResult.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError:
        return None


def save_ocr(path: Path, result: OcrPageResult) -> None:
    """Atomically write an OCR cache JSON file.

    Args:
        path: Destination OCR cache path.
        result: OCR result to serialize.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
    ) as tmp_file:
        tmp_file.write(result.model_dump_json())
        tmp_path = Path(tmp_file.name)
    tmp_path.replace(path)
