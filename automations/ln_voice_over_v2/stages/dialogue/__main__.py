"""Module-mode CLI for the LNVO v2 dialogue stage."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ...common import paths
from ...common.errors import ContractValidationError
from .agent import DEFAULT_DIALOGUE_TIMEOUT_SECONDS
from .chunking import DEFAULT_MAX_CANDIDATES_PER_CHUNK
from .runner import (
    DialogueConfig,
    DialogueVolumeConfig,
    run_dialogue,
    run_dialogue_volume,
)


def main(argv: list[str] | None = None) -> int:
    """Run the dialogue-stage CLI.

    With `--chapter`, attribute that one chapter. Without it, attribute every
    chapter in the volume index, dispatching `--workers` chapters concurrently.

    Args:
        argv: Optional argument vector. Defaults to `sys.argv[1:]`.

    Returns:
        Process-style exit code.
    """
    _configure_logging()
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except argparse.ArgumentError as exc:
        parser.print_usage(sys.stderr)
        sys.stderr.write(f"{parser.prog}: error: {exc}\n")
        return 2

    if args.chapter is not None:
        return _run_single_chapter(args)
    return _run_volume(args)


def _run_single_chapter(args: argparse.Namespace) -> int:
    config = DialogueConfig(
        series=args.series,
        volume=args.volume,
        chapter_id=args.chapter,
        data_root=args.data_root,
        force=args.force,
        timeout_seconds=args.timeout,
        max_candidates_per_chunk=args.max_candidates_per_chunk,
    )
    try:
        result = run_dialogue(config)
    except ContractValidationError as exc:
        _write_problems(exc)
        return 2
    except Exception as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    sys.stdout.write(f"{result.dialogue_path}\n")
    return 0


def _run_volume(args: argparse.Namespace) -> int:
    config = DialogueVolumeConfig(
        series=args.series,
        volume=args.volume,
        data_root=args.data_root,
        force=args.force,
        workers=args.workers,
        timeout_seconds=args.timeout,
        max_candidates_per_chunk=args.max_candidates_per_chunk,
    )
    try:
        result = run_dialogue_volume(config)
    except ContractValidationError as exc:
        _write_problems(exc)
        return 2
    except Exception as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    for outcome in result.outcomes:
        if outcome.error is not None:
            sys.stderr.write(f"{outcome.chapter_id}: error: {outcome.error}\n")
        elif outcome.result is not None and outcome.result.skipped:
            sys.stdout.write(f"{outcome.chapter_id}: skipped (exists)\n")
        elif outcome.result is not None:
            sys.stdout.write(f"{outcome.result.dialogue_path}\n")

    sys.stdout.write(
        f"dialogue: {result.written} written, {result.skipped} skipped, {result.failed} failed\n"
    )
    return 1 if result.failed else 0


def _write_problems(exc: ContractValidationError) -> None:
    for problem in exc.problems:
        sys.stderr.write(f"{problem.code}: {problem.path}: {problem.message}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m automations.ln_voice_over_v2.stages.dialogue",
        exit_on_error=False,
    )
    parser.add_argument("--series", required=True)
    parser.add_argument("--volume", required=True)
    parser.add_argument(
        "--chapter", help="Chapter id (e.g. chapter_01). Omit to run every chapter."
    )
    parser.add_argument("--data-root", type=Path, default=paths.DEFAULT_PROJECT_DATA_ROOT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Concurrent chapters when running the whole volume (default 4).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_DIALOGUE_TIMEOUT_SECONDS,
        help=(
            "Codex subprocess timeout in seconds per chapter "
            f"(default {DEFAULT_DIALOGUE_TIMEOUT_SECONDS})."
        ),
    )
    parser.add_argument(
        "--max-candidates-per-chunk",
        type=int,
        default=DEFAULT_MAX_CANDIDATES_PER_CHUNK,
        help=(
            "Maximum dialogue candidates per Codex attribution chunk "
            f"(default {DEFAULT_MAX_CANDIDATES_PER_CHUNK})."
        ),
    )
    return parser


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if any(getattr(handler, "_lnvo_dialogue_handler", False) for handler in root_logger.handlers):
        return

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler._lnvo_dialogue_handler = True  # type: ignore[attr-defined]
    root_logger.addHandler(handler)


if __name__ == "__main__":
    raise SystemExit(main())
