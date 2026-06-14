"""Codex-backed dialogue attribution agent."""

import subprocess

from pydantic import BaseModel, ConfigDict, ValidationError

from ...common.errors import ContractValidationError, ValidationProblem
from ...common.ids import SegmentId
from .contracts import SpeakerGender

# Default per-chapter codex attribution timeout in seconds. Shared by the config
# and CLI defaults so the value never drifts across the call chain.
DEFAULT_DIALOGUE_TIMEOUT_SECONDS = 600


class CandidateDecision(BaseModel):
    """Dialogue classification decision for one candidate segment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    segment_id: SegmentId
    is_dialogue: bool
    speaker_raw: str | None = None
    speaker_gender: SpeakerGender = "unknown"
    reason: str = ""


class DialogueProposal(BaseModel):
    """Raw model proposal before deterministic normalization."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decisions: tuple[CandidateDecision, ...]
    narrator_raw: str | None = None
    review_notes: tuple[str, ...] = ()


def run_codex_dialogue(
    prompt: str,
    *,
    model: str = "gpt-5.5",
    executable: str = "codex",
    timeout_seconds: int = DEFAULT_DIALOGUE_TIMEOUT_SECONDS,
) -> DialogueProposal:
    """Run Codex in text-only mode and parse a dialogue proposal."""
    argv = [
        executable,
        "exec",
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
        completed = subprocess.run(  # noqa: UP022 - contract requires explicit stdout/stderr pipes.
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=True,
        )
    # `from None` suppresses the chained subprocess error: its `cmd`/`argv`
    # carries the full prompt, which must not leak into a printed traceback.
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"codex dialogue timed out after {timeout_seconds}s") from None
    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"codex dialogue failed: {err.stderr}") from None

    try:
        return DialogueProposal.model_validate_json(completed.stdout.strip())
    except ValidationError as parse_err:
        raise ContractValidationError(
            [
                ValidationProblem(
                    code="dialogue_malformed",
                    message=str(parse_err)[:500],
                    path="<dialogue>",
                )
            ]
        ) from parse_err
