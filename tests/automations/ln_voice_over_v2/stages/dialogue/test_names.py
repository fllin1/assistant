"""Name normalization tests for the dialogue stage."""

from __future__ import annotations

from automations.ln_voice_over_v2.pipeline.validators import UNKNOWN_SPEAKER
from automations.ln_voice_over_v2.series.contracts import Character, CharacterRegistry
from automations.ln_voice_over_v2.stages.dialogue.names import (
    canonical_narrator,
    canonical_speaker,
)


def test_character_registry_resolve_exact_name_alias_and_miss() -> None:
    """The registry resolves exact canonical names and aliases only."""
    registry = _registry()

    assert registry.resolve("Horikita Suzune") == "Horikita Suzune"
    assert registry.resolve(" Horikita ") == "Horikita Suzune"
    assert registry.resolve("Unknown Student") is None


def test_canonical_speaker_resolves_alias_to_canonical() -> None:
    """Speaker aliases normalize to canonical names."""
    assert canonical_speaker("Horikita", _registry()) == "Horikita Suzune"


def test_canonical_speaker_unknown_and_empty_values_use_unknown() -> None:
    """Unresolved, empty, and null speaker labels become `Unknown`."""
    registry = _registry()

    assert canonical_speaker("Mystery Student", registry) == UNKNOWN_SPEAKER
    assert canonical_speaker(None, registry) == UNKNOWN_SPEAKER
    assert canonical_speaker("  ", registry) == UNKNOWN_SPEAKER


def test_canonical_speaker_first_person_uses_narrator() -> None:
    """First-person speaker tags resolve to the already-canonical narrator."""
    registry = _registry()

    assert (
        canonical_speaker("I.", registry, narrator="Ayanokouji Kiyotaka") == "Ayanokouji Kiyotaka"
    )


def test_canonical_narrator_resolves_alias_and_miss() -> None:
    """Narrator aliases normalize, while unresolved labels return `None`."""
    registry = _registry()

    assert canonical_narrator("Ayanokouji", registry) == "Ayanokouji Kiyotaka"
    assert canonical_narrator("Mystery Student", registry) is None
    assert canonical_narrator(None, registry) is None
    assert canonical_narrator("  ", registry) is None


def _registry() -> CharacterRegistry:
    return CharacterRegistry(
        characters=(
            Character(name="Ayanokouji Kiyotaka", aliases=("Ayanokouji",), role="main"),
            Character(name="Horikita Suzune", aliases=("Horikita",), role="main"),
        )
    )
