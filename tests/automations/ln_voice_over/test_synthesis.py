"""Tests for LNVO voice mapping import and synthesis planning."""

from __future__ import annotations

import io
import json
import sqlite3
import wave
from pathlib import Path
from typing import Any

import pytest
from automations.ln_voice_over import cli, synthesis
from automations.ln_voice_over import config as lnvo_config
from automations.ln_voice_over.models import (
    Chapter,
    Character,
    CharacterRegistry,
    NarratorStatus,
    Segment,
    SegmentType,
)
from automations.ln_voice_over.synthesis import (
    EngineInfo,
    SynthesisPreflightError,
    build_synthesis_plan,
    prepare_tts_text,
    synthesis_cache_key,
)
from automations.ln_voice_over.voice_mapping import (
    VoiceMappingEntry,
    import_voice_mapping_from_voice_tuning,
    save_voice_mapping,
    voice_mapping_path,
)
from typer.testing import CliRunner


@pytest.fixture
def registry() -> CharacterRegistry:
    return CharacterRegistry(
        characters=(
            Character(name="Ayanokouji Kiyotaka", aliases=("Ayanokouji",), gender="male"),
            Character(name="Horikita Suzune", aliases=("Horikita",), gender="female"),
        )
    )


def make_chapter(
    *segments: Segment,
    narrator: str | None = "Ayanokouji Kiyotaka",
    narrator_status: NarratorStatus = NarratorStatus.DETECTED,
) -> Chapter:
    return Chapter(
        chapter_number=1,
        title="Test",
        source_file="chapter_01.txt",
        narrator_status=narrator_status,
        narrator=narrator,
        segments=segments,
        reviewed=True,
    )


def segment(
    index: int,
    segment_type: SegmentType,
    text: str,
    speaker: str | None,
) -> Segment:
    return Segment(index=index, segment_type=segment_type, text=text, speaker=speaker)


def engine_infos() -> dict[str, EngineInfo]:
    return {
        "kokoro": EngineInfo("kokoro", "kokoro-test-v1", True),
        "orpheus": EngineInfo("orpheus", "orpheus-test-v1", True),
        "hume": EngineInfo("hume", "hume-test-v1", True),
    }


def voice_mapping() -> dict[str, VoiceMappingEntry]:
    return {
        "Ayanokouji Kiyotaka": VoiceMappingEntry(
            engine="hume",
            voice_id="ayanokoji-voice",
            params={"description": "calm"},
        ),
        "Horikita Suzune": VoiceMappingEntry(engine="kokoro", voice_id="af_sarah"),
        "Narrator": VoiceMappingEntry(engine="orpheus", voice_id="dan"),
        "Unknown": VoiceMappingEntry(engine="orpheus", voice_id="dan"),
    }


def tiny_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24_000)
        wav.writeframes(b"\x01\x00" * 240)
    return buf.getvalue()


def create_voice_tuning_db(root: Path) -> None:
    root.mkdir(parents=True)
    db_path = root / "voice-tuning.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE results (
                id INTEGER PRIMARY KEY,
                engine TEXT NOT NULL,
                voice_id TEXT NOT NULL,
                speed REAL NOT NULL,
                params_json TEXT
            );
            CREATE TABLE casting (
                character_slot TEXT PRIMARY KEY,
                result_id INTEGER REFERENCES results(id)
            );
            CREATE TABLE voice_notes (
                engine TEXT NOT NULL,
                voice_id TEXT NOT NULL,
                slot TEXT NOT NULL,
                params_fp TEXT NOT NULL DEFAULT '',
                playback_speed REAL
            );
            """
        )
        params = json.dumps({"description": "calm"})
        conn.execute(
            "INSERT INTO results VALUES (1, 'hume', 'ayanokoji-voice', 1.0, ?)",
            (params,),
        )
        conn.execute("INSERT INTO casting VALUES ('ayanokoji', 1)")
        params_fp = json.dumps({"description": "calm"}, sort_keys=True, separators=(",", ":"))
        conn.execute(
            "INSERT INTO voice_notes VALUES ('hume', 'ayanokoji-voice', 'ayanokoji', ?, 0.95)",
            (params_fp,),
        )
        conn.commit()


def test_prepare_tts_text_strips_only_balanced_dialogue_outer_quotes():
    assert (
        prepare_tts_text(segment(0, SegmentType.DIALOGUE, '"Hello there."', "Horikita Suzune"))
        == "Hello there."
    )
    assert (
        prepare_tts_text(
            segment(0, SegmentType.DIALOGUE, "\u201cHello there.\u201d", "Horikita Suzune")
        )
        == "Hello there."
    )
    assert (
        prepare_tts_text(
            segment(0, SegmentType.DIALOGUE, '"She said \u201ctrap\u201d."', "Horikita Suzune")
        )
        == "She said \u201ctrap\u201d."
    )
    assert (
        prepare_tts_text(segment(0, SegmentType.DIALOGUE, '"Mismatched.\u201d', "Horikita Suzune"))
        == '"Mismatched.\u201d'
    )
    assert (
        prepare_tts_text(segment(0, SegmentType.NARRATION, '"Quoted thought."', "Narrator"))
        == '"Quoted thought."'
    )


def test_voice_mapping_import_uses_selected_cast_and_gender_fallback(
    tmp_path: Path,
    registry: CharacterRegistry,
):
    voice_tuning_root = tmp_path / "voice-tuning"
    create_voice_tuning_db(voice_tuning_root)

    mapping = import_voice_mapping_from_voice_tuning(registry, voice_tuning_root)

    assert mapping["Ayanokouji Kiyotaka"].engine == "hume"
    assert mapping["Ayanokouji Kiyotaka"].voice_id == "ayanokoji-voice"
    assert mapping["Ayanokouji Kiyotaka"].params == {"description": "calm"}
    assert mapping["Ayanokouji Kiyotaka"].playback_speed == 0.95
    assert mapping["Horikita Suzune"].engine == "kokoro"
    assert mapping["Horikita Suzune"].voice_id == "af_sarah"
    assert mapping["Narrator"].engine == "orpheus"
    assert mapping["Unknown"].engine == "orpheus"


def test_preflight_rejects_missing_voice_mapping_key(
    tmp_path: Path,
    registry: CharacterRegistry,
):
    chapter = make_chapter(
        segment(0, SegmentType.DIALOGUE, '"Hello."', "Horikita Suzune"),
    )
    mapping = voice_mapping()
    del mapping["Horikita Suzune"]

    with pytest.raises(SynthesisPreflightError, match="voice mapping missing key"):
        build_synthesis_plan(chapter, registry, mapping, tmp_path, "01", engine_infos())


def test_preflight_rejects_legacy_unset_or_noncanonical_reviewed_data(
    tmp_path: Path,
    registry: CharacterRegistry,
):
    legacy_null = make_chapter(
        segment(0, SegmentType.NARRATION, "Text.", None),
    )
    with pytest.raises(SynthesisPreflightError, match='must use speaker "Narrator"'):
        build_synthesis_plan(
            legacy_null, registry, voice_mapping(), tmp_path, "01", engine_infos()
        )

    unset = make_chapter(
        segment(0, SegmentType.NARRATION, "Text.", "Narrator"),
        narrator_status=NarratorStatus.UNSET,
        narrator=None,
    )
    with pytest.raises(SynthesisPreflightError, match="narrator detection has not run"):
        build_synthesis_plan(unset, registry, voice_mapping(), tmp_path, "01", engine_infos())

    unresolved = make_chapter(
        segment(0, SegmentType.DIALOGUE, '"Hello."', "Mystery Person"),
    )
    with pytest.raises(SynthesisPreflightError, match="Registry gap"):
        build_synthesis_plan(unresolved, registry, voice_mapping(), tmp_path, "01", engine_infos())


def test_narrator_voice_resolution_uses_character_or_omniscient_key(
    tmp_path: Path,
    registry: CharacterRegistry,
):
    first_person = make_chapter(
        segment(0, SegmentType.NARRATION, "Text.", "Narrator"),
        narrator="Ayanokouji Kiyotaka",
    )
    first_plan = build_synthesis_plan(
        first_person,
        registry,
        voice_mapping(),
        tmp_path,
        "01",
        engine_infos(),
    )
    assert first_plan.segments[0].voice_key == "Ayanokouji Kiyotaka"

    omniscient = make_chapter(
        segment(0, SegmentType.NARRATION, "Text.", "Narrator"),
        narrator=None,
    )
    omni_plan = build_synthesis_plan(
        omniscient,
        registry,
        voice_mapping(),
        tmp_path,
        "01",
        engine_infos(),
    )
    assert omni_plan.segments[0].voice_key == "Narrator"


def test_cache_key_is_stable_and_invalidates_on_content_changes():
    entry = VoiceMappingEntry(engine="kokoro", voice_id="af_sarah", params={"a": 1})

    key = synthesis_cache_key(
        engine_version="v1",
        entry=entry,
        text="Hello",
        segment_type=SegmentType.DIALOGUE,
    )

    assert key == synthesis_cache_key(
        engine_version="v1",
        entry=entry,
        text="Hello",
        segment_type=SegmentType.DIALOGUE,
    )
    assert key != synthesis_cache_key(
        engine_version="v1",
        entry=entry,
        text="Hello!",
        segment_type=SegmentType.DIALOGUE,
    )
    assert key != synthesis_cache_key(
        engine_version="v1",
        entry=entry.model_copy(update={"voice_id": "af_bella"}),
        text="Hello",
        segment_type=SegmentType.DIALOGUE,
    )


def test_voice_map_import_cli_writes_series_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: CharacterRegistry,
):
    voice_tuning_root = tmp_path / "voice-tuning"
    create_voice_tuning_db(voice_tuning_root)
    monkeypatch.setattr(lnvo_config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(cli, "load_characters", lambda _series: registry)

    result = CliRunner().invoke(
        cli.app,
        [
            "voice-map",
            "import",
            "series",
            "--voice-tuning-root",
            str(voice_tuning_root),
        ],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(voice_mapping_path("series").read_text(encoding="utf-8"))
    assert set(data) == {"Ayanokouji Kiyotaka", "Horikita Suzune", "Narrator", "Unknown"}


class FakeBridge:
    def __init__(self, _root: Path) -> None:
        self.render_calls: list[list[dict[str, Any]]] = []

    def inspect_engines(self) -> dict[str, EngineInfo]:
        return engine_infos()

    def render_segments(
        self,
        requests: list[dict[str, Any]],
        progress: Any | None = None,
    ) -> dict[int, bytes]:
        self.render_calls.append(requests)
        if progress:
            total = len(requests)
            for ordinal, request in enumerate(requests, start=1):
                progress(
                    {
                        "event": "render_segment_start",
                        "ordinal": ordinal,
                        "total": total,
                        "index": request["index"],
                        "engine": request["engine"],
                        "voice_key": request["voice_key"],
                        "text_chars": len(request["text"]),
                    }
                )
        return {int(request["index"]): tiny_wav() for request in requests}


def write_synthesis_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: CharacterRegistry,
) -> Path:
    projects = tmp_path / "projects"
    monkeypatch.setattr(lnvo_config, "PROJECTS_DIR", projects)
    monkeypatch.setattr(cli, "load_characters", lambda _series: registry)
    series_config = projects / "series" / "config"
    volume = projects / "series" / "v1"
    chapter = make_chapter(
        segment(0, SegmentType.DIALOGUE, '"Hello."', "Horikita Suzune"),
        narrator=None,
    )
    chapter.save(volume / "reviewed" / "chapter_01.json")
    save_voice_mapping(series_config / "voice_mapping.json", voice_mapping())
    return volume


def test_synthesize_cli_decline_exits_before_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: CharacterRegistry,
):
    write_synthesis_fixture(tmp_path, monkeypatch, registry)
    fake = FakeBridge(tmp_path / "voice-tuning")
    monkeypatch.setattr(synthesis, "VoiceTuningBridge", lambda _root: fake)

    result = CliRunner().invoke(
        cli.app,
        ["synthesize", "series/v1", "1", "--voice-tuning-root", str(tmp_path / "voice-tuning")],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    assert "Aborted before rendering." in result.output
    assert fake.render_calls == []


def test_synthesize_cli_yes_renders_non_empty_wav(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: CharacterRegistry,
):
    volume = write_synthesis_fixture(tmp_path, monkeypatch, registry)
    fake = FakeBridge(tmp_path / "voice-tuning")
    monkeypatch.setattr(synthesis, "VoiceTuningBridge", lambda _root: fake)

    result = CliRunner().invoke(
        cli.app,
        [
            "synthesize",
            "series/v1",
            "1",
            "--voice-tuning-root",
            str(tmp_path / "voice-tuning"),
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    output_path = volume / "audio" / "chapter_01.wav"
    manifest_path = volume / "audio" / "chapter_01.manifest.json"
    assert output_path.stat().st_size > 44
    assert manifest_path.exists()
    assert fake.render_calls
    assert "Rendering 1 uncached segment(s)..." in result.output
    assert "Rendering 1/1: segment 0 (kokoro, Horikita Suzune, 6 chars)" in result.output
    assert "Concatenating" in result.output
