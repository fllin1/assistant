"""Voice mapping import and validation for LN synthesis."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .config import series_dir
from .models import Character, CharacterRegistry

DEFAULT_VOICE_TUNING_ROOT = Path.home() / "_workspace" / "tools" / "voice-tuning"
VOICE_MAPPING_FILENAME = "voice_mapping.json"

ORPHEUS_STANDARD_PARAMS = {
    "temperature": 0.7,
    "top_p": 0.85,
    "top_k": 50,
    "repetition_penalty": 1.3,
}

MALE_FALLBACK = {
    "engine": "orpheus",
    "voice_id": "dan",
    "speed": 1.0,
    "params": ORPHEUS_STANDARD_PARAMS,
    "playback_speed": 1.0,
}

FEMALE_FALLBACK = {
    "engine": "kokoro",
    "voice_id": "af_sarah",
    "speed": 1.0,
    "params": {},
    "playback_speed": 1.0,
}

FIXED_VOICE_TUNING_SLOTS = {
    "Ayanokouji Kiyotaka": "ayanokoji",
    "Horikita Suzune": "horikita",
    "Karuizawa Kei": "karuizawa",
    "Kushida Kikyou": "kushida_public",
    "Kushida Kikyou (private)": "kushida_private",
    "Ichinose Honami": "ichinose",
    "Sakayanagi Arisu": "sakayanagi",
    "Ryuuen Kakeru": "ryuen",
}


class VoiceMappingError(ValueError):
    """Raised when a voice mapping file or import source is invalid."""


class VoiceMappingEntry(BaseModel):
    """Accepted TTS voice configuration for one canonical speaker key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    engine: str
    voice_id: str
    speed: float = 1.0
    params: dict[str, Any] = Field(default_factory=dict)
    playback_speed: float = 1.0


VoiceMapping = dict[str, VoiceMappingEntry]


def voice_mapping_path(series_slug: str) -> Path:
    """Return the canonical series-level voice mapping path."""
    return series_dir(series_slug) / "config" / VOICE_MAPPING_FILENAME


def load_voice_mapping(path: Path) -> VoiceMapping:
    """Load a voice mapping from disk."""
    if not path.exists():
        raise VoiceMappingError(f"voice mapping not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise VoiceMappingError("voice mapping must be a JSON object keyed by speaker")
    return {key: VoiceMappingEntry.model_validate(value) for key, value in data.items()}


def save_voice_mapping(path: Path, mapping: Mapping[str, VoiceMappingEntry]) -> None:
    """Save a voice mapping atomically."""
    payload = {key: entry.model_dump(mode="json") for key, entry in mapping.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.rename(path)


def import_voice_mapping_from_voice_tuning(
    registry: CharacterRegistry,
    voice_tuning_root: Path = DEFAULT_VOICE_TUNING_ROOT,
) -> VoiceMapping:
    """Create an accepted voice mapping from the voice-tuning selected cast."""
    cast = _load_voice_tuning_cast(voice_tuning_root)
    slots = voice_tuning_slots_for_registry(registry)
    mapping: VoiceMapping = {}

    for character in registry.characters:
        slot = slots[character.name]
        mapping[character.name] = cast.get(slot, _fallback_for_character(character))

    mapping[registry.narrator_name] = _entry_from_raw(MALE_FALLBACK)
    mapping["Unknown"] = _entry_from_raw(MALE_FALLBACK)
    return mapping


def voice_tuning_slots_for_registry(registry: CharacterRegistry) -> dict[str, str]:
    """Return the voice-tuning slot key for each registry character."""
    used = {
        "ayanokoji",
        "horikita",
        "karuizawa",
        "kushida_public",
        "kushida_private",
        "ichinose",
        "sakayanagi",
        "ryuen",
        "kushida",
    }
    slots: dict[str, str] = {}

    for character in registry.characters:
        fixed = FIXED_VOICE_TUNING_SLOTS.get(character.name)
        if fixed is not None:
            slots[character.name] = fixed
            continue

        base = _slug_for_voice_tuning(character.name)
        slot = base
        if slot in used:
            tokens = character.name.split()
            second = _ascii_slug(tokens[1]) if len(tokens) > 1 else "x"
            slot = f"{base}_{second}"
        used.add(slot)
        slots[character.name] = slot

    return slots


def _load_voice_tuning_cast(voice_tuning_root: Path) -> dict[str, VoiceMappingEntry]:
    db_path = voice_tuning_root / "voice-tuning.db"
    if not db_path.exists():
        raise VoiceMappingError(f"voice-tuning database not found: {db_path}")

    query = """
        SELECT
          c.character_slot,
          r.engine,
          r.voice_id,
          r.speed,
          r.params_json
        FROM casting c
        JOIN results r ON r.id = c.result_id
    """
    cast: dict[str, VoiceMappingEntry] = {}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(query):
            params = _decode_params(row["params_json"])
            note = conn.execute(
                "SELECT playback_speed FROM voice_notes "
                "WHERE engine = ? AND voice_id = ? AND slot = ? AND params_fp = ?",
                (
                    row["engine"],
                    row["voice_id"],
                    row["character_slot"],
                    _params_fingerprint(params),
                ),
            ).fetchone()
            playback_speed = (
                float(note["playback_speed"])
                if note and note["playback_speed"] is not None
                else 1.0
            )
            cast[row["character_slot"]] = VoiceMappingEntry(
                engine=row["engine"],
                voice_id=row["voice_id"],
                speed=float(row["speed"]),
                params=params,
                playback_speed=playback_speed,
            )
    return cast


def _decode_params(params_json: str | None) -> dict[str, Any]:
    if not params_json:
        return {}
    value = json.loads(params_json)
    if not isinstance(value, dict):
        raise VoiceMappingError("voice-tuning params_json must decode to an object")
    return value


def _params_fingerprint(params: Mapping[str, Any]) -> str:
    if not params:
        return ""
    return json.dumps(dict(params), sort_keys=True, separators=(",", ":"))


def _fallback_for_character(character: Character) -> VoiceMappingEntry:
    if character.gender == "female":
        return _entry_from_raw(FEMALE_FALLBACK)
    return _entry_from_raw(MALE_FALLBACK)


def _entry_from_raw(raw: Mapping[str, Any]) -> VoiceMappingEntry:
    return VoiceMappingEntry.model_validate(raw)


def _slug_for_voice_tuning(name: str) -> str:
    head = name.split()[0] if name.split() else name
    return _ascii_slug(head)


def _ascii_slug(value: str) -> str:
    return (
        value.replace("ō", "o")
        .replace("Ō", "o")
        .replace("ū", "u")
        .replace("Ū", "u")
        .replace("ä", "a")
        .replace("ē", "e")
        .replace("ī", "i")
        .lower()
    )
