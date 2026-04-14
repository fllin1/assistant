"""Entity resolution: map raw speaker names to canonical character names.

Takes extraction results (flat {index: speaker} dicts) and resolves names
against the CharacterRegistry. Supports cross-validation across multiple
sources and flags unresolved/divergent attributions for review.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
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
    """Resolve a raw name to a canonical character name.

    Returns the canonical name or None if unresolved.
    """
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
) -> tuple[Chapter, list[dict]]:
    """Resolve raw attributions to canonical names and produce an attributed chapter.

    For each dialogue segment:
    - "Narrator" → reclassify as NARRATION, speaker = None
    - "Unknown" → keep, flag for review
    - Name → resolve via registry, flag if unresolved
    - Missing → flag as missing

    Returns:
        (attributed_chapter, flags) where flags is a list of dicts
        describing unresolved/missing attributions.
    """
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
            new_segments.append(replace(seg, segment_type=SegmentType.NARRATION, speaker=None))
            continue

        if raw == "Unknown":
            flags.append(
                {"index": seg.index, "type": "unknown", "raw": raw, "text": seg.text[:80]}
            )
            new_segments.append(replace(seg, speaker="Unknown"))
            continue

        canonical = _resolve_name(raw, registry)
        if canonical:
            new_segments.append(replace(seg, speaker=canonical))
        else:
            flags.append(
                {"index": seg.index, "type": "unresolved", "raw": raw, "text": seg.text[:80]}
            )
            new_segments.append(replace(seg, speaker=raw))

    attributed = replace(chapter, segments=tuple(new_segments))
    return attributed, flags


def cross_validate(
    sources: dict[str, dict[str, str]],
    registry: CharacterRegistry,
) -> tuple[dict[str, str], list[dict]]:
    """Cross-validate attributions from multiple sources.

    For each dialogue index:
    - All sources agree (after canonical resolution) → consensus
    - Sources disagree → flag divergence
    - Only one source has it → flag for review
    - No source → flag as missing

    Returns:
        (consensus_attributions, divergences)
    """
    all_indices: set[str] = set()
    for source in sources.values():
        all_indices.update(source.keys())

    consensus: dict[str, str] = {}
    divergences: list[dict] = []

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
            divergences.append(
                {"index": idx, "type": "single_source", "source": source_name, "value": raw}
            )
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
            consensus[idx] = next(iter(values.values()))
        else:
            # Divergence — pick majority, or first source as tiebreaker
            from collections import Counter

            counts = Counter(resolved.values())
            winner = counts.most_common(1)[0][0]
            # Find original raw value for the winner
            for source_name, canon in resolved.items():
                if canon == winner:
                    consensus[idx] = values[source_name]
                    break
            divergences.append({"index": idx, "type": "divergence", "sources": dict(values)})

    return consensus, divergences
