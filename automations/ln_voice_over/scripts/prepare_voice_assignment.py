"""Prepare a voice-assignment plan for a series or specific volume.

Aggregates dialogue-line counts per character across reviewed chapters
(falling back to resolved/), classifies each into tiers S/A/B/C/D, and
reports the list alongside currently-assigned voices and the available
voice catalog. The `/assign-voices` skill consumes the JSON output and
proposes voice assignments following the strategy in `docs/6-voice-assignment.md`.

Usage:
    python -m automations.ln_voice_over.scripts.prepare_voice_assignment \\
        <series-slug>[/<volume-slug>] [--include-tier-d]

When a volume is given, the dialogue counts come from that volume only.
When only a series is given, counts aggregate across every volume that
has reviewed/ or resolved/ chapters.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from automations.ln_voice_over.models import Chapter, SegmentType
from automations.ln_voice_over.project import (
    list_volumes,
    load_characters,
    load_voices,
    parse_slug,
)
from automations.ln_voice_over.providers.kokoro import KOKORO_VOICES
from automations.ln_voice_over.providers.openai import OPENAI_VOICES

# Curated Edge en-US voice set from docs/6-voice-assignment.md. The full
# Edge catalog is 47 English voices; these are the 13 we recommend for
# character assignment (clear, neutral, no strong accents).
EDGE_EN_US_VOICES: list[dict[str, str]] = [
    {"voice_id": "en-US-AndrewNeural", "gender": "male"},
    {"voice_id": "en-US-BrianNeural", "gender": "male"},
    {"voice_id": "en-US-ChristopherNeural", "gender": "male"},
    {"voice_id": "en-US-EricNeural", "gender": "male"},
    {"voice_id": "en-US-GuyNeural", "gender": "male"},
    {"voice_id": "en-US-RogerNeural", "gender": "male"},
    {"voice_id": "en-US-SteffanNeural", "gender": "male"},
    {"voice_id": "en-US-AriaNeural", "gender": "female"},
    {"voice_id": "en-US-AvaNeural", "gender": "female"},
    {"voice_id": "en-US-EmmaNeural", "gender": "female"},
    {"voice_id": "en-US-JennyNeural", "gender": "female"},
    {"voice_id": "en-US-MichelleNeural", "gender": "female"},
    {"voice_id": "en-US-AnaNeural", "gender": "female"},
]

# Tier thresholds: (lower_bound_inclusive, label). Matched top-down.
TIER_THRESHOLDS: list[tuple[int, str]] = [
    (500, "S"),
    (100, "A"),
    (20, "B"),
    (5, "C"),
    (0, "D"),
]


def classify_tier(line_count: int) -> str:
    """Return the tier letter for a given dialogue-line count."""
    for threshold, label in TIER_THRESHOLDS:
        if line_count >= threshold:
            return label
    return "D"


def count_dialogue_per_speaker(volume_path: Path) -> Counter[str]:
    """Count dialogue segments per speaker in a volume's reviewed or resolved chapters.

    Prefers reviewed/ (corrected by human) over resolved/ (LLM output).
    Returns a Counter keyed by speaker name.
    """
    stage_dir = volume_path / "reviewed"
    if not stage_dir.exists() or not any(stage_dir.glob("chapter_*.json")):
        stage_dir = volume_path / "resolved"
    if not stage_dir.exists():
        return Counter()

    counts: Counter[str] = Counter()
    for path in sorted(stage_dir.glob("chapter_*.json")):
        if path.name.endswith("_flags.json"):
            continue
        chapter = Chapter.load(path)
        for seg in chapter.segments:
            if seg.segment_type == SegmentType.DIALOGUE and seg.speaker:
                counts[seg.speaker] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="<series> or <series>/<volume>")
    parser.add_argument(
        "--include-tier-d",
        action="store_true",
        help="Include Tier D (<5 lines) in output. Default: omit (gender defaults suffice).",
    )
    args = parser.parse_args()

    series_slug, volume_slug = parse_slug(args.target)
    specific_volume = "/" in args.target  # user passed an explicit volume

    registry = load_characters(series_slug)
    voices = load_voices(series_slug)
    assigned = {
        m.speaker: {"voice_id": m.voice_id, "provider": m.provider} for m in voices.mappings
    }

    # Determine which volumes to aggregate over.
    if specific_volume:
        volumes_to_scan = [volume_slug]
    else:
        volumes_to_scan = list_volumes(series_slug)

    per_volume_counts: dict[str, Counter[str]] = {}
    total_counts: Counter[str] = Counter()
    for vol in volumes_to_scan:
        from automations.ln_voice_over.config import volume_dir

        counts = count_dialogue_per_speaker(volume_dir(series_slug, vol))
        per_volume_counts[vol] = dict(counts)
        total_counts.update(counts)

    # Build per-character report. Iterate the registry (not the counter) so
    # registered characters with 0 dialogue still appear (useful for walk-ons
    # that exist in the registry but never speak in the scanned volumes).
    characters_report: list[dict] = []
    for char in registry.characters:
        # Count lines attributed to this character's canonical name or any alias.
        lines = total_counts.get(char.name, 0)
        for alias in char.aliases:
            lines += total_counts.get(alias, 0)
        tier = classify_tier(lines)
        if not args.include_tier_d and tier == "D":
            continue
        characters_report.append(
            {
                "name": char.name,
                "aliases": list(char.aliases),
                "gender": char.gender,
                "role": char.role,
                "description": char.description,
                "lines": lines,
                "tier": tier,
                "current_voice": assigned.get(char.name),
            }
        )

    # Sort by lines desc so the LLM agent sees the most important first.
    characters_report.sort(key=lambda c: (-c["lines"], c["name"]))

    output = {
        "series": series_slug,
        "volumes_scanned": volumes_to_scan,
        "tier_thresholds": [
            {"tier": "S", "min_lines": 500, "strategy": "OpenAI voice — protagonist/narrator"},
            {"tier": "A", "min_lines": 100, "strategy": "OpenAI voice — major character"},
            {"tier": "B", "min_lines": 20, "strategy": "Kokoro American voice — supporting"},
            {"tier": "C", "min_lines": 5, "strategy": "Kokoro/Edge voice — minor"},
            {"tier": "D", "min_lines": 0, "strategy": "Skip — gender default suffices"},
        ],
        "defaults": {
            "narrator": voices.default_narrator.voice_id,
            "male": voices.default_male.voice_id,
            "female": voices.default_female.voice_id,
        },
        "characters": characters_report,
        "available_voices": {
            "openai": [{"voice_id": v["voice_id"], "gender": v["gender"]} for v in OPENAI_VOICES],
            "kokoro_american": [
                {"voice_id": v["voice_id"], "gender": v["gender"]}
                for v in KOKORO_VOICES
                if v.get("accent") == "American"
            ],
            "kokoro_british": [
                {"voice_id": v["voice_id"], "gender": v["gender"]}
                for v in KOKORO_VOICES
                if v.get("accent") == "British"
            ],
            "edge_en_us": EDGE_EN_US_VOICES,
        },
    }

    # Augment with a "voices_in_use" list so the agent doesn't double-assign.
    output["voices_in_use"] = sorted({m.voice_id for m in voices.mappings})

    json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
