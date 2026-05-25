"""Module-mode CLI for the LNVO v2 prepare stage."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ...common import paths
from ...common.errors import ContractValidationError
from .runner import PrepareConfig, run_prepare


def main(argv: list[str] | None = None) -> int:
    """Run the prepare-stage CLI.

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

    config = PrepareConfig(
        anyflip_url=args.url,
        series=args.series,
        volume=args.volume,
        data_root=args.data_root,
        story_profile=args.story_profile,
        ocr_model=args.ocr_model,
        workers=args.workers,
        force=args.force,
        force_ocr=args.force_ocr,
    )

    try:
        result = run_prepare(config)
    except ContractValidationError as exc:
        for problem in exc.problems:
            sys.stderr.write(f"{problem.code}: {problem.path}: {problem.message}\n")
        return 2
    except Exception as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    sys.stdout.write(f"{result.prepared_volume_path}\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m automations.ln_voice_over_v2.stages.prepare",
        exit_on_error=False,
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--series", required=True)
    parser.add_argument("--volume", required=True)
    parser.add_argument("--story-profile")
    parser.add_argument("--data-root", type=Path, default=paths.DEFAULT_PROJECT_DATA_ROOT)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--ocr-model", default="gpt-5-mini")
    force_group = parser.add_mutually_exclusive_group()
    force_group.add_argument("--force", action="store_true")
    force_group.add_argument("--force-ocr", action="store_true")
    return parser


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if any(getattr(handler, "_lnvo_prepare_handler", False) for handler in root_logger.handlers):
        return

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler._lnvo_prepare_handler = True  # type: ignore[attr-defined]
    root_logger.addHandler(handler)


if __name__ == "__main__":
    raise SystemExit(main())
