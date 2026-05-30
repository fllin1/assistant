"""Name normalization helpers for dialogue attribution."""

from __future__ import annotations

from ...pipeline.validators import UNKNOWN_SPEAKER
from ...series.contracts import CharacterRegistry

FIRST_PERSON_TAGS = frozenset({"i", "me", "myself", "i."})


def canonical_speaker(
    raw: str | None, registry: CharacterRegistry, narrator: str | None = None
) -> str:
    """Resolve a raw speaker label to a canonical character name or `Unknown`.

    Args:
        raw: Raw model-proposed speaker label.
        registry: Series character registry used for exact name and alias lookup.
        narrator: Already-canonical narrator name used for first-person tags.

    Returns:
        A canonical character name, the narrator for first-person labels when
        provided, or `Unknown` when the label cannot be resolved.
    """
    if raw is None:
        return UNKNOWN_SPEAKER

    candidate = raw.strip()
    if not candidate:
        return UNKNOWN_SPEAKER

    if candidate.casefold() in FIRST_PERSON_TAGS and narrator is not None:
        return narrator

    return registry.resolve(candidate) or UNKNOWN_SPEAKER


def canonical_narrator(raw: str | None, registry: CharacterRegistry) -> str | None:
    """Resolve a raw narrator label to a canonical character name when possible.

    Args:
        raw: Raw model-proposed narrator label.
        registry: Series character registry used for exact name and alias lookup.

    Returns:
        Canonical narrator name when resolved; otherwise `None`.
    """
    if raw is None:
        return None

    candidate = raw.strip()
    if not candidate:
        return None

    return registry.resolve(candidate)
