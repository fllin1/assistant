"""Tests for Stage 8: SYNTHESIZE — pure logic (voice resolution, cache, gaps).

Orchestration (synthesize_segment, assemble_chapter) needs live TTS/ffmpeg
and lives under the "live" pytest marker instead.
"""

from __future__ import annotations

from automations.ln_voice_over.models import (
    Chapter,
    Character,
    CharacterRegistry,
    Segment,
    SegmentType,
    VoiceConfig,
    VoiceMapping,
)
from automations.ln_voice_over.synthesize import (
    _speed_for,
    _speed_settings,
    cache_key,
    compute_settings,
    gap_ms,
    resolve_voice,
    strip_dialogue_quotes,
)


def _segment(idx: int, seg_type: SegmentType, text: str = "text", speaker: str | None = None):
    return Segment(index=idx, segment_type=seg_type, text=text, speaker=speaker)


def _chapter(pov: str | None = None, segments: tuple[Segment, ...] = ()) -> Chapter:
    return Chapter(
        chapter_number=1,
        title="t",
        source_file="chapter_01.txt",
        pov_character=pov,
        segments=segments,
    )


def _registry(*chars: Character) -> CharacterRegistry:
    return CharacterRegistry(characters=chars)


def _voices(
    mappings: tuple[VoiceMapping, ...] = (),
    host: VoiceMapping | None = None,
) -> VoiceConfig:
    return VoiceConfig(mappings=mappings, host=host)


class TestResolveVoice:
    def test_scene_break_is_silence(self):
        seg = _segment(0, SegmentType.SCENE_BREAK, text="")
        assert resolve_voice(seg, _chapter(), _voices(), _registry()) is None

    def test_chapter_header_uses_narrator_when_no_host(self):
        seg = _segment(0, SegmentType.CHAPTER_HEADER, text="Chapter 1")
        voices = _voices()
        assert resolve_voice(seg, _chapter(), voices, _registry()) == voices.default_narrator

    def test_chapter_header_uses_host_when_set(self):
        host = VoiceMapping(speaker="Protagonist", provider="openai", voice_id="echo")
        voices = _voices(host=host)
        seg = _segment(0, SegmentType.CHAPTER_HEADER, text="Chapter 1")
        assert resolve_voice(seg, _chapter(), voices, _registry()) == host

    def test_narration_without_pov_uses_narrator(self):
        seg = _segment(0, SegmentType.NARRATION)
        voices = _voices()
        assert (
            resolve_voice(seg, _chapter(pov=None), voices, _registry()) == voices.default_narrator
        )

    def test_narration_with_pov_uses_pov_mapping(self):
        pov_mapping = VoiceMapping(speaker="Hero", provider="openai", voice_id="echo")
        voices = _voices((pov_mapping,))
        registry = _registry(Character(name="Hero", gender="male", role="main"))
        seg = _segment(0, SegmentType.NARRATION)
        assert resolve_voice(seg, _chapter(pov="Hero"), voices, registry) == pov_mapping

    def test_narration_with_pov_not_in_registry_falls_back_to_narrator(self):
        voices = _voices()
        seg = _segment(0, SegmentType.NARRATION)
        assert (
            resolve_voice(seg, _chapter(pov="Ghost"), voices, _registry())
            == voices.default_narrator
        )

    def test_dialogue_without_speaker_uses_narrator(self):
        seg = _segment(0, SegmentType.DIALOGUE, speaker=None)
        voices = _voices()
        assert resolve_voice(seg, _chapter(), voices, _registry()) == voices.default_narrator

    def test_dialogue_with_mapped_speaker_uses_speaker_voice(self):
        speaker_mapping = VoiceMapping(speaker="Hero", provider="edge", voice_id="en-US-GuyNeural")
        voices = _voices((speaker_mapping,))
        registry = _registry(Character(name="Hero", gender="male", role="main"))
        seg = _segment(0, SegmentType.DIALOGUE, speaker="Hero")
        assert resolve_voice(seg, _chapter(), voices, registry) == speaker_mapping

    def test_dialogue_unmapped_speaker_uses_gender_default(self):
        voices = _voices()
        registry = _registry(Character(name="Hero", gender="male", role="main"))
        seg = _segment(0, SegmentType.DIALOGUE, speaker="Hero")
        assert resolve_voice(seg, _chapter(), voices, registry) == voices.default_male

    def test_dialogue_unknown_speaker_falls_back_to_narrator(self):
        voices = _voices()
        seg = _segment(0, SegmentType.DIALOGUE, speaker="Ghost")
        assert resolve_voice(seg, _chapter(), voices, _registry()) == voices.default_narrator


class TestCacheKey:
    def test_is_deterministic(self):
        m = VoiceMapping(speaker="x", provider="edge", voice_id="v1")
        assert cache_key(m, "hello") == cache_key(m, "hello")

    def test_differs_by_provider(self):
        m1 = VoiceMapping(speaker="x", provider="edge", voice_id="v1")
        m2 = VoiceMapping(speaker="x", provider="openai", voice_id="v1")
        assert cache_key(m1, "hello") != cache_key(m2, "hello")

    def test_differs_by_voice_id(self):
        m1 = VoiceMapping(speaker="x", provider="edge", voice_id="v1")
        m2 = VoiceMapping(speaker="x", provider="edge", voice_id="v2")
        assert cache_key(m1, "hello") != cache_key(m2, "hello")

    def test_differs_by_text(self):
        m = VoiceMapping(speaker="x", provider="edge", voice_id="v1")
        assert cache_key(m, "hello") != cache_key(m, "world")

    def test_length_is_16_hex_chars(self):
        m = VoiceMapping(speaker="x", provider="edge", voice_id="v1")
        key = cache_key(m, "hello")
        assert len(key) == 16
        int(key, 16)  # must parse as hex

    def test_none_settings_equals_empty_settings(self):
        # Both should produce the same hash as the legacy 3-argument form,
        # so changing "no settings" representation doesn't invalidate caches.
        m = VoiceMapping(speaker="x", provider="edge", voice_id="v1")
        assert cache_key(m, "hello", None) == cache_key(m, "hello", {})
        assert cache_key(m, "hello", None) == cache_key(m, "hello")

    def test_differs_by_settings(self):
        m = VoiceMapping(speaker="x", provider="openai", voice_id="nova")
        assert cache_key(m, "hello", {"speed": 1.05}) != cache_key(m, "hello", {"speed": 1.10})
        assert cache_key(m, "hello", {"speed": 1.05}) != cache_key(m, "hello")

    def test_settings_key_order_does_not_matter(self):
        m = VoiceMapping(speaker="x", provider="edge", voice_id="v1")
        a = cache_key(m, "hello", {"pitch": "+5Hz", "rate": "+5%"})
        b = cache_key(m, "hello", {"rate": "+5%", "pitch": "+5Hz"})
        assert a == b


class TestGapMs:
    def test_first_segment_has_no_leading_silence(self):
        assert gap_ms(None, SegmentType.NARRATION) == 0
        assert gap_ms(None, SegmentType.DIALOGUE) == 0

    def test_chapter_header_always_gets_long_lead(self):
        assert gap_ms(SegmentType.NARRATION, SegmentType.CHAPTER_HEADER) == 1100
        assert gap_ms(SegmentType.DIALOGUE, SegmentType.CHAPTER_HEADER) == 1100

    def test_dialogue_to_dialogue_is_150(self):
        assert gap_ms(SegmentType.DIALOGUE, SegmentType.DIALOGUE) == 150

    def test_narration_to_dialogue_is_300(self):
        assert gap_ms(SegmentType.NARRATION, SegmentType.DIALOGUE) == 300

    def test_dialogue_to_narration_is_300(self):
        assert gap_ms(SegmentType.DIALOGUE, SegmentType.NARRATION) == 300

    def test_narration_to_narration_uses_default(self):
        assert gap_ms(SegmentType.NARRATION, SegmentType.NARRATION) == 300

    def test_scene_break_neighbours_get_zero_gap(self):
        assert gap_ms(SegmentType.NARRATION, SegmentType.SCENE_BREAK) == 0
        assert gap_ms(SegmentType.SCENE_BREAK, SegmentType.NARRATION) == 0


class TestStripDialogueQuotes:
    def test_strips_straight_quotes(self):
        assert strip_dialogue_quotes('"hello"') == "hello"

    def test_strips_curly_quotes(self):
        assert strip_dialogue_quotes("\u201chello\u201d") == "hello"

    def test_strips_mixed_pair(self):
        assert strip_dialogue_quotes('\u201chello"') == "hello"

    def test_leaves_unmatched_alone(self):
        assert strip_dialogue_quotes('"hello') == '"hello'
        assert strip_dialogue_quotes('hello"') == 'hello"'

    def test_leaves_interior_quotes_alone(self):
        assert strip_dialogue_quotes('she said "hi" loudly') == 'she said "hi" loudly'

    def test_short_strings_pass_through(self):
        assert strip_dialogue_quotes("") == ""
        assert strip_dialogue_quotes('"') == '"'


class TestSpeedPolicy:
    def test_narration_speed(self):
        assert _speed_for(SegmentType.NARRATION) == 1.15

    def test_header_speed(self):
        assert _speed_for(SegmentType.CHAPTER_HEADER) == 1.15

    def test_dialogue_speed(self):
        assert _speed_for(SegmentType.DIALOGUE) == 1.20

    def test_unit_speed_emits_no_settings(self):
        # Cache-hygiene — speed == 1.0 must not add a no-op settings entry,
        # otherwise we'd invalidate every voice's cache the first time the
        # policy is introduced.
        assert _speed_settings("edge", 1.0) == {}
        assert _speed_settings("openai", 1.0) == {}
        assert _speed_settings("kokoro", 1.0) == {}

    def test_openai_uses_float_speed(self):
        assert _speed_settings("openai", 1.10) == {"speed": 1.10}

    def test_kokoro_uses_float_speed(self):
        assert _speed_settings("kokoro", 1.05) == {"speed": 1.05}

    def test_edge_uses_rate_percent_string(self):
        assert _speed_settings("edge", 1.05) == {"rate": "+5%"}
        assert _speed_settings("edge", 1.10) == {"rate": "+10%"}

    def test_edge_handles_slowdown(self):
        assert _speed_settings("edge", 0.90) == {"rate": "-10%"}

    def test_compute_settings_applies_policy_when_no_override(self):
        m = VoiceMapping(speaker="x", provider="openai", voice_id="nova")
        assert compute_settings(m, SegmentType.DIALOGUE) == {"speed": 1.20}
        assert compute_settings(m, SegmentType.NARRATION) == {"speed": 1.15}

    def test_compute_settings_mapping_override_wins(self):
        # Per-mapping settings are authoritative — the voice config is the
        # user's override for a character with a distinctive pace.
        m = VoiceMapping(speaker="x", provider="openai", voice_id="nova", settings={"speed": 0.85})
        assert compute_settings(m, SegmentType.DIALOGUE) == {"speed": 0.85}

    def test_compute_settings_mapping_extra_keys_merge(self):
        # Override on a key the policy doesn't touch — both should survive.
        m = VoiceMapping(speaker="x", provider="edge", voice_id="v1", settings={"pitch": "+5Hz"})
        out = compute_settings(m, SegmentType.NARRATION)
        assert out == {"rate": "+15%", "pitch": "+5Hz"}
