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
    cache_key,
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


def _voices(mappings: tuple[VoiceMapping, ...] = ()) -> VoiceConfig:
    return VoiceConfig(mappings=mappings)


class TestResolveVoice:
    def test_scene_break_is_silence(self):
        seg = _segment(0, SegmentType.SCENE_BREAK, text="")
        assert resolve_voice(seg, _chapter(), _voices(), _registry()) is None

    def test_chapter_header_uses_narrator(self):
        seg = _segment(0, SegmentType.CHAPTER_HEADER, text="Chapter 1")
        voices = _voices()
        assert resolve_voice(seg, _chapter(), voices, _registry()) == voices.default_narrator

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

    def test_narration_with_pov_not_in_registry_falls_back_to_male_default(self):
        # POV name is set but no mapping and no registry entry => gender "unknown"
        # => falls through to default_narrator (not male/female default).
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
        # No mapping for "Hero" => falls back to default_male by gender
        assert resolve_voice(seg, _chapter(), voices, registry) == voices.default_male

    def test_dialogue_unknown_speaker_falls_back_to_narrator(self):
        # Speaker is set but not in registry and not in mappings =>
        # get_voice runs with gender "unknown" => default_narrator.
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


class TestGapMs:
    def test_first_segment_has_no_leading_silence(self):
        assert gap_ms(None, SegmentType.NARRATION) == 0
        assert gap_ms(None, SegmentType.DIALOGUE) == 0

    def test_chapter_header_always_gets_long_lead(self):
        assert gap_ms(SegmentType.NARRATION, SegmentType.CHAPTER_HEADER) == 1500
        assert gap_ms(SegmentType.DIALOGUE, SegmentType.CHAPTER_HEADER) == 1500

    def test_dialogue_to_dialogue_is_200(self):
        assert gap_ms(SegmentType.DIALOGUE, SegmentType.DIALOGUE) == 200

    def test_narration_to_dialogue_is_400(self):
        assert gap_ms(SegmentType.NARRATION, SegmentType.DIALOGUE) == 400

    def test_dialogue_to_narration_is_400(self):
        assert gap_ms(SegmentType.DIALOGUE, SegmentType.NARRATION) == 400

    def test_narration_to_narration_uses_default(self):
        assert gap_ms(SegmentType.NARRATION, SegmentType.NARRATION) == 400

    def test_scene_break_neighbours_get_zero_gap(self):
        # The break itself produces 800ms of silence; the surrounding gap is 0.
        assert gap_ms(SegmentType.NARRATION, SegmentType.SCENE_BREAK) == 0
        assert gap_ms(SegmentType.SCENE_BREAK, SegmentType.NARRATION) == 0


class TestStripDialogueQuotes:
    def test_strips_straight_quotes(self):
        assert strip_dialogue_quotes('"hello"') == "hello"

    def test_strips_curly_quotes(self):
        assert strip_dialogue_quotes("\u201chello\u201d") == "hello"

    def test_strips_mixed_pair(self):
        # Opener curly, closer straight — still a matched pair at boundaries.
        assert strip_dialogue_quotes('\u201chello"') == "hello"

    def test_leaves_unmatched_alone(self):
        assert strip_dialogue_quotes('"hello') == '"hello'
        assert strip_dialogue_quotes('hello"') == 'hello"'

    def test_leaves_interior_quotes_alone(self):
        assert strip_dialogue_quotes('she said "hi" loudly') == 'she said "hi" loudly'

    def test_short_strings_pass_through(self):
        assert strip_dialogue_quotes("") == ""
        assert strip_dialogue_quotes('"') == '"'
