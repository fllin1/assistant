"""Entity resolution: map raw speaker names to canonical character names.

Takes extraction results (flat {index: speaker} dicts) and resolves names
against the CharacterRegistry. Supports cross-validation across multiple
sources and flags unresolved/divergent attributions for review.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

from .models import Chapter, CharacterRegistry, SegmentType

logger = logging.getLogger(__name__)


def load_extracted(path: Path) -> dict[str, str]:
    """Load a flat {index: speaker} dict from an extracted file.

    Handles two formats:
    - Flat JSON: {"3": "Horikita", "6": "Chabashira-sensei", ...}
    - Legacy experiment results: [{"index": 3, "resolved_mention": "Horikita"}, ...]
    """
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, list):
        return {str(r["index"]): r["resolved_mention"] for r in data if r.get("resolved_mention")}

    return {str(k): v for k, v in data.items()}


def _resolve_name(name: str, registry: CharacterRegistry) -> str | None:
    """Resolve a raw name to a canonical character name."""
    char = registry.find(name)
    if char:
        return char.name

    char = registry.fuzzy_find(name)
    if char:
        return char.name

    return None


def resolve_chapter(
    chapter: Chapter,
    attributions: dict[str, str],
    registry: CharacterRegistry,
    confirmed_unknowns: set[str] | None = None,
) -> tuple[Chapter, list[dict]]:
    """Resolve raw attributions to canonical names and produce an attributed chapter.

    For each dialogue segment:
    - "Narrator" → reclassify as NARRATION, speaker = None
    - "Unknown" → keep, flag only if not in confirmed_unknowns
    - Name → resolve via registry, flag if unresolved
    - Missing → flag as missing

    Args:
        confirmed_unknowns: Indices where multiple sources agreed on "Unknown".
            These are genuinely unnamed characters and don't need review.
    """
    confirmed = confirmed_unknowns or set()
    flags: list[dict] = []
    new_segments = []

    for seg in chapter.segments:
        if seg.segment_type not in (SegmentType.DIALOGUE, SegmentType.INNER_THOUGHT):
            new_segments.append(seg)
            continue

        raw = attributions.get(str(seg.index))

        if raw is None:
            flags.append({"index": seg.index, "type": "missing", "text": seg.text[:80]})
            new_segments.append(seg)
            continue

        if raw == "Narrator":
            new_segments.append(
                seg.model_copy(update={"segment_type": SegmentType.NARRATION, "speaker": None})
            )
            continue

        if raw == "Unknown":
            # Only flag if not confirmed by multiple sources
            if str(seg.index) not in confirmed:
                flags.append(
                    {"index": seg.index, "type": "unknown", "raw": raw, "text": seg.text[:80]}
                )
            new_segments.append(seg.model_copy(update={"speaker": "Unknown"}))
            continue

        canonical = _resolve_name(raw, registry)
        if canonical:
            new_segments.append(seg.model_copy(update={"speaker": canonical}))
        else:
            flags.append(
                {"index": seg.index, "type": "unresolved", "raw": raw, "text": seg.text[:80]}
            )
            new_segments.append(seg.model_copy(update={"speaker": raw}))

    attributed = chapter.model_copy(update={"segments": tuple(new_segments)})
    return attributed, flags


def cross_validate(
    sources: dict[str, dict[str, str]],
    registry: CharacterRegistry,
) -> tuple[dict[str, str], list[dict], set[str]]:
    """Cross-validate attributions from multiple sources.

    For each dialogue index:
    - All sources agree (after canonical resolution) → consensus
    - One says Unknown, other resolves to known character → prefer the name
    - Sources disagree → flag divergence, pick majority
    - Only one source has it → use it (no flag)
    - No source → flag as missing

    Returns:
        (consensus_attributions, divergences, confirmed_unknowns)
        confirmed_unknowns: indices where all sources agreed on "Unknown"
    """
    all_indices: set[str] = set()
    for source in sources.values():
        all_indices.update(source.keys())

    consensus: dict[str, str] = {}
    divergences: list[dict] = []
    confirmed_unknowns: set[str] = set()

    for idx in sorted(all_indices, key=int):
        values: dict[str, str] = {}
        for name, source in sources.items():
            if idx in source:
                values[name] = source[idx]

        if not values:
            divergences.append({"index": idx, "type": "missing"})
            continue

        if len(values) == 1:
            source_name, raw = next(iter(values.items()))
            consensus[idx] = raw
            continue

        # Resolve all to canonical for comparison
        resolved: dict[str, str] = {}
        for source_name, raw in values.items():
            if raw in ("Narrator", "Unknown"):
                resolved[source_name] = raw
            else:
                canonical = _resolve_name(raw, registry)
                resolved[source_name] = canonical or raw

        unique = set(resolved.values())

        if len(unique) == 1:
            # All sources agree
            consensus[idx] = next(iter(values.values()))
            if next(iter(unique)) == "Unknown":
                confirmed_unknowns.add(idx)
            continue

        # One source says Unknown, another found a name — prefer the name if it resolves
        if "Unknown" in unique and len(unique) == 2:
            named = {s: r for s, r in resolved.items() if r != "Unknown"}
            if named:
                winner_source = next(iter(named))
                if _resolve_name(values[winner_source], registry):
                    consensus[idx] = values[winner_source]
                    continue

        # Divergence — pick majority, or first source as tiebreaker
        counts = Counter(resolved.values())
        winner = counts.most_common(1)[0][0]
        for source_name, canon in resolved.items():
            if canon == winner:
                consensus[idx] = values[source_name]
                break
        divergences.append({"index": idx, "type": "divergence", "sources": dict(values)})

    return consensus, divergences, confirmed_unknowns
