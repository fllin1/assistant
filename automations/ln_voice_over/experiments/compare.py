"""Compare extraction experiment results against ground truth.

Loads an experiment's results.json and compares resolved_mention
against the ground truth speaker for each dialogue segment.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


def _normalize_name(name: str) -> str:
    """Lowercase, strip, and remove honorifics for comparison."""
    n = name.lower().strip()
    for suffix in ("-sensei", "-san", "-kun", "-chan", "-sama", "-senpai"):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
            break
    return n


def _build_alias_map(registry_path: Path | None) -> dict[str, str]:
    """Build a mapping from any known name/alias to canonical name.

    Returns {normalized_alias: canonical_name} dict.
    """
    if registry_path is None or not registry_path.exists():
        return {}

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    alias_map: dict[str, str] = {}
    for char in data.get("characters", []):
        canonical = char["name"]
        alias_map[_normalize_name(canonical)] = canonical
        for alias in char.get("aliases", []):
            alias_map[_normalize_name(alias)] = canonical
    return alias_map


def _resolve_to_canonical(name: str, alias_map: dict[str, str]) -> str:
    """Resolve a name to its canonical form using the alias map."""
    normalized = _normalize_name(name)
    if normalized in alias_map:
        return alias_map[normalized]
    # Try partial match: check if any alias is a substring
    for alias, canonical in alias_map.items():
        if alias in normalized or normalized in alias:
            return canonical
    return name


def _speaker_match(resolved: str, gt_speaker: str, alias_map: dict[str, str]) -> bool:
    """Check if resolved mention matches ground truth speaker.

    Uses the character registry alias map for robust matching:
    "Mii-chan" → "Wang Mei-Yu", "Horikita" → "Horikita Suzune", etc.
    """
    # Direct match
    if _normalize_name(resolved) == _normalize_name(gt_speaker):
        return True

    # Resolve both through registry
    canonical_resolved = _resolve_to_canonical(resolved, alias_map)
    canonical_gt = _resolve_to_canonical(gt_speaker, alias_map)
    if canonical_resolved == canonical_gt:
        return True

    # Fallback: substring match on name parts
    r = _normalize_name(resolved)
    gt_parts = _normalize_name(gt_speaker).split()
    if r in gt_parts:
        return True
    return any(part in r for part in gt_parts if len(part) > 2)


def compare_to_ground_truth(
    experiment_path: Path,
    ground_truth_path: Path,
    registry_path: Path | None = None,
) -> dict:
    """Compare extraction results against ground truth.

    Args:
        experiment_path: Path to experiment directory (contains results.json).
        ground_truth_path: Path to ground truth JSON (index -> speaker mapping).
        registry_path: Path to characters.json for alias resolution.

    Returns:
        Dict with accuracy metrics and detailed errors.
    """
    results = json.loads((experiment_path / "results.json").read_text(encoding="utf-8"))
    gt = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    alias_map = _build_alias_map(registry_path)

    total = 0
    correct = 0
    wrong = 0
    no_mention = 0
    errors: list[dict] = []

    mention_type_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0})
    speaker_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0})

    for result in results:
        idx = str(result["index"])
        if idx not in gt:
            continue

        total += 1
        gt_speaker = gt[idx]
        resolved = result.get("resolved_mention")
        mention_type = result.get("mention_type", "none")

        mention_type_stats[mention_type]["total"] += 1
        speaker_stats[gt_speaker]["total"] += 1

        if resolved is None or resolved.strip() == "":
            no_mention += 1
            wrong += 1
            errors.append(
                {
                    "index": result["index"],
                    "gt": gt_speaker,
                    "resolved": None,
                    "raw_mention": result.get("raw_mention"),
                    "mention_type": mention_type,
                    "reasoning": result.get("reasoning", ""),
                    "error_type": "no_mention",
                }
            )
        elif _speaker_match(resolved, gt_speaker, alias_map):
            correct += 1
            mention_type_stats[mention_type]["correct"] += 1
            speaker_stats[gt_speaker]["correct"] += 1
        else:
            wrong += 1
            errors.append(
                {
                    "index": result["index"],
                    "gt": gt_speaker,
                    "resolved": resolved,
                    "raw_mention": result.get("raw_mention"),
                    "mention_type": mention_type,
                    "mention_source_index": result.get("mention_source_index"),
                    "reasoning": result.get("reasoning", ""),
                    "error_type": "wrong_speaker",
                    "_source_valid": result.get("_source_valid"),
                }
            )
            speaker_stats[gt_speaker]["total"] += 0  # already counted

    comparison = {
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "no_mention": no_mention,
        "accuracy": correct / total if total else 0,
        "mention_type_stats": {k: dict(v) for k, v in mention_type_stats.items()},
        "speaker_stats": {k: dict(v) for k, v in speaker_stats.items()},
        "errors": errors,
    }

    # Save comparison
    (experiment_path / "comparison.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return comparison


def format_comparison_report(comparison: dict) -> str:
    """Format a comparison report as a string."""
    lines: list[str] = []
    total = comparison["total"]
    correct = comparison["correct"]
    wrong = comparison["wrong"]
    no_mention = comparison["no_mention"]
    accuracy = comparison["accuracy"]

    lines.append(f"\n{'=' * 70}")
    lines.append("EXTRACTION EXPERIMENT — COMPARISON REPORT")
    lines.append(f"{'=' * 70}")
    lines.append(f"Total: {total}  Correct: {correct}  Wrong: {wrong}  Accuracy: {accuracy:.1%}")
    lines.append(f"No mention: {no_mention}  Wrong speaker: {wrong - no_mention}")

    # Mention type breakdown
    lines.append(f"\n{'─' * 70}")
    lines.append("BY MENTION TYPE")
    lines.append(f"{'─' * 70}")
    lines.append(f"  {'Type':<15s} {'Total':>6s} {'Correct':>8s} {'Accuracy':>9s}")
    for mtype, stats in sorted(comparison["mention_type_stats"].items()):
        acc = stats["correct"] / stats["total"] if stats["total"] else 0
        lines.append(f"  {mtype:<15s} {stats['total']:>6d} {stats['correct']:>8d} {acc:>8.1%}")

    # Per-speaker breakdown (top 15 by count)
    lines.append(f"\n{'─' * 70}")
    lines.append("BY GROUND TRUTH SPEAKER (top 15)")
    lines.append(f"{'─' * 70}")
    lines.append(f"  {'Speaker':<30s} {'Total':>6s} {'Correct':>8s} {'Accuracy':>9s}")
    sorted_speakers = sorted(comparison["speaker_stats"].items(), key=lambda x: -x[1]["total"])
    for speaker, stats in sorted_speakers[:15]:
        acc = stats["correct"] / stats["total"] if stats["total"] else 0
        marker = " <<<" if acc < 0.7 and stats["total"] >= 3 else ""
        lines.append(
            f"  {speaker:<30s} {stats['total']:>6d} {stats['correct']:>8d} {acc:>8.1%}{marker}"
        )

    # Sample errors
    errors = comparison["errors"]
    if errors:
        wrong_sp = [e for e in errors if e["error_type"] == "wrong_speaker"]
        no_m = [e for e in errors if e["error_type"] == "no_mention"]

        if wrong_sp:
            lines.append(f"\n{'─' * 70}")
            lines.append(f"WRONG SPEAKER ERRORS (showing first 20 of {len(wrong_sp)})")
            lines.append(f"{'─' * 70}")
            for e in wrong_sp[:20]:
                lines.append(
                    f"  [{e['index']:>4d}] GT={e['gt']:<25s} Got={e['resolved']:<25s} "
                    f"[{e['mention_type']}] {e['reasoning'][:60]}"
                )

        if no_m:
            lines.append(f"\n{'─' * 70}")
            lines.append(f"NO MENTION ERRORS (showing first 10 of {len(no_m)})")
            lines.append(f"{'─' * 70}")
            for e in no_m[:10]:
                lines.append(f"  [{e['index']:>4d}] GT={e['gt']:<25s} raw={e['raw_mention']}")

    return "\n".join(lines)
