"""Tests for Stage 4: ATTRIBUTE — speaker attribution via LLM."""

from unittest.mock import patch

from automations.ln_voice_over.attribute import (
    attribute_chapter,
    attribute_chapter_per_dialogue,
    attribute_narration,
    create_windows,
)
from automations.ln_voice_over.models import (
    Chapter,
    Character,
    CharacterRegistry,
    Segment,
    SegmentType,
)
from automations.ln_voice_over.prompts import (
    build_attribution_prompt,
    build_system_prompt,
    parse_attribution_response,
)


def _seg(index: int, seg_type: SegmentType, text: str = "text") -> Segment:
    return Segment(index=index, segment_type=seg_type, text=text, line_start=1, line_end=1)


def _chapter(segments: list[Segment], pov: str | None = None) -> Chapter:
    return Chapter(
        chapter_number=1,
        title="Test",
        source_file="test.txt",
        pov_character=pov,
        segments=tuple(segments),
    )


REGISTRY = CharacterRegistry(
    characters=(
        Character(name="Alice", aliases=("A",), gender="female", role="main"),
        Character(name="Bob", aliases=("B",), gender="male", role="supporting"),
    ),
    narrator_name="Narrator",
)


class TestCreateWindows:
    def test_single_window(self):
        segs = [_seg(i, SegmentType.NARRATION) for i in range(10)]
        windows = create_windows(segs, window_size=40, overlap=8)
        assert len(windows) == 1
        assert len(windows[0]) == 10

    def test_multiple_windows(self):
        segs = [_seg(i, SegmentType.NARRATION) for i in range(100)]
        windows = create_windows(segs, window_size=40, overlap=8)
        assert len(windows) >= 3
        # Each window should have at most window_size segments
        for w in windows:
            assert len(w) <= 40

    def test_overlap(self):
        segs = [_seg(i, SegmentType.NARRATION) for i in range(80)]
        windows = create_windows(segs, window_size=40, overlap=8)
        # Windows should overlap — last 8 of window 0 = first 8 of window 1
        last_of_first = [s.index for s in windows[0][-8:]]
        first_of_second = [s.index for s in windows[1][:8]]
        assert last_of_first == first_of_second

    def test_accepts_tuple(self):
        segs = tuple(_seg(i, SegmentType.NARRATION) for i in range(5))
        windows = create_windows(segs, window_size=40, overlap=8)
        assert len(windows) == 1


class TestAttributeNarration:
    def test_narration_gets_narrator(self):
        ch = _chapter(
            [
                _seg(0, SegmentType.CHAPTER_HEADER),
                _seg(1, SegmentType.NARRATION),
                _seg(2, SegmentType.DIALOGUE, '"Hello."'),
            ]
        )

        result = attribute_narration(ch)

        assert result.segments[0].speaker == "Narrator"
        assert result.segments[0].confidence == 1.0
        assert result.segments[1].speaker == "Narrator"
        assert result.segments[1].confidence == 1.0
        # Dialogue left untouched
        assert result.segments[2].speaker is None

    def test_narration_with_pov_character(self):
        ch = _chapter(
            [_seg(0, SegmentType.NARRATION), _seg(1, SegmentType.CHAPTER_HEADER)],
            pov="Alice",
        )

        result = attribute_narration(ch)

        assert result.segments[0].speaker == "Alice"
        # Header always gets narrator, not POV
        assert result.segments[1].speaker == "Narrator"

    def test_immutability(self):
        ch = _chapter([_seg(0, SegmentType.NARRATION)])
        result = attribute_narration(ch)

        # Original unchanged
        assert ch.segments[0].speaker is None
        assert result.segments[0].speaker == "Narrator"


class TestBuildSystemPrompt:
    def test_returns_string(self):
        prompt = build_system_prompt()
        assert isinstance(prompt, str)
        assert "JSON" in prompt
        assert "dialogue" in prompt.lower()


class TestBuildAttributionPrompt:
    def test_includes_characters(self):
        segs = [_seg(0, SegmentType.DIALOGUE, '"Hello."')]
        prompt = build_attribution_prompt(segs, REGISTRY)
        assert "Alice" in prompt
        assert "Bob" in prompt

    def test_includes_segments(self):
        segs = [_seg(0, SegmentType.DIALOGUE, '"Hello."')]
        prompt = build_attribution_prompt(segs, REGISTRY)
        assert "Hello." in prompt
        assert "dialogue" in prompt

    def test_includes_previous_context(self):
        segs = [_seg(5, SegmentType.DIALOGUE, '"Goodbye."')]
        prev = [{"index": 3, "segment_type": "dialogue", "text": '"Hi."', "speaker": "Alice"}]
        prompt = build_attribution_prompt(segs, REGISTRY, previous_attributions=prev)
        assert "Alice" in prompt
        assert "Previous" in prompt


class TestParseAttributionResponse:
    def test_valid_json(self):
        response = '[{"index": 0, "speaker": "Alice", "confidence": 0.9}]'
        result = parse_attribution_response(response)
        assert len(result) == 1
        assert result[0]["index"] == 0
        assert result[0]["speaker"] == "Alice"
        assert result[0]["confidence"] == 0.9

    def test_markdown_fences(self):
        response = '```json\n[{"index": 0, "speaker": "Alice", "confidence": 0.8}]\n```'
        result = parse_attribution_response(response)
        assert len(result) == 1
        assert result[0]["speaker"] == "Alice"

    def test_invalid_json_returns_empty(self):
        result = parse_attribution_response("not json at all")
        assert result == []

    def test_missing_fields_skipped(self):
        response = '[{"index": 0, "speaker": "Alice", "confidence": 0.9}, {"index": 1}]'
        result = parse_attribution_response(response)
        assert len(result) == 1

    def test_confidence_clamped(self):
        response = '[{"index": 0, "speaker": "Alice", "confidence": 1.5}]'
        result = parse_attribution_response(response)
        assert result[0]["confidence"] == 1.0

    def test_object_wrapper(self):
        response = '{"attributions": [{"index": 0, "speaker": "Bob", "confidence": 0.7}]}'
        result = parse_attribution_response(response)
        assert len(result) == 1
        assert result[0]["speaker"] == "Bob"


class TestAttributeChapter:
    @patch("automations.ln_voice_over.attribute._call_llm")
    def test_dialogue_gets_speakers(self, mock_llm):
        mock_llm.return_value = '[{"index": 2, "speaker": "Alice", "confidence": 0.9}]'

        ch = _chapter(
            [
                _seg(0, SegmentType.CHAPTER_HEADER, "Chapter 1: Test"),
                _seg(1, SegmentType.NARRATION, "She walked in."),
                _seg(2, SegmentType.DIALOGUE, '"Hello."'),
            ]
        )

        result = attribute_chapter(ch, REGISTRY)

        assert result.segments[0].speaker == "Narrator"
        assert result.segments[1].speaker == "Narrator"
        assert result.segments[2].speaker == "Alice"
        assert result.segments[2].confidence == 0.9

    @patch("automations.ln_voice_over.attribute._call_llm")
    def test_unattributed_dialogue_gets_unknown(self, mock_llm):
        # LLM returns empty — dialogue should fallback to Unknown
        mock_llm.return_value = "[]"

        ch = _chapter(
            [
                _seg(0, SegmentType.NARRATION, "He spoke."),
                _seg(1, SegmentType.DIALOGUE, '"Hey."'),
            ]
        )

        result = attribute_chapter(ch, REGISTRY)

        assert result.segments[1].speaker == "Unknown"
        assert result.segments[1].confidence == 0.0

    @patch("automations.ln_voice_over.attribute._call_llm")
    def test_no_llm_call_without_dialogue(self, mock_llm):
        ch = _chapter(
            [
                _seg(0, SegmentType.CHAPTER_HEADER, "Chapter 1"),
                _seg(1, SegmentType.NARRATION, "Just narration."),
            ]
        )

        attribute_chapter(ch, REGISTRY)

        mock_llm.assert_not_called()


class TestRegistryFuzzyFind:
    """Tests for CharacterRegistry.fuzzy_find() and validate_speaker()."""

    def test_exact_match(self):
        result = REGISTRY.fuzzy_find("Alice")
        assert result is not None
        assert result.name == "Alice"

    def test_alias_match(self):
        result = REGISTRY.fuzzy_find("A")
        assert result is not None
        assert result.name == "Alice"

    def test_honorific_stripped(self):
        result = REGISTRY.fuzzy_find("Alice-sensei")
        assert result is not None
        assert result.name == "Alice"

    def test_fuzzy_close_match(self):
        result = REGISTRY.fuzzy_find("Alce")
        assert result is not None
        assert result.name == "Alice"

    def test_no_match(self):
        result = REGISTRY.fuzzy_find("Zzzzzzz")
        assert result is None

    def test_validate_exact(self):
        name, conf = REGISTRY.validate_speaker("Alice", 0.9)
        assert name == "Alice"
        assert conf == 0.9

    def test_validate_fuzzy_penalizes(self):
        name, conf = REGISTRY.validate_speaker("Alce", 0.9)
        assert name == "Alice"
        assert conf == 0.9 * 0.8

    def test_validate_unknown(self):
        name, conf = REGISTRY.validate_speaker("Zzzzzzz", 0.9)
        assert name == "Unknown"
        assert conf == 0.0


class TestAttributeChapterPerDialogueIntegration:
    """Integration tests for the improved per-dialogue attribution."""

    @patch("automations.ln_voice_over.attribute._call_llm")
    def test_llm_fallback_with_validation(self, mock_llm):
        """When regex fails, LLM result is validated against registry."""
        mock_llm.return_value = '[{"index": 1, "speaker": "Alce", "confidence": 0.9}]'

        ch = _chapter(
            [
                _seg(0, SegmentType.NARRATION, "The room was quiet."),
                _seg(1, SegmentType.DIALOGUE, '"Hello."'),
                _seg(2, SegmentType.NARRATION, "The door closed."),
            ]
        )

        result = attribute_chapter_per_dialogue(ch, REGISTRY)

        mock_llm.assert_called_once()
        # "Alce" fuzzy-matches to "Alice"
        assert result.segments[1].speaker == "Alice"
        assert result.segments[1].attribution_method == "per_dialogue_llm"

    @patch("automations.ln_voice_over.attribute._call_llm")
    def test_hallucinated_name_rejected(self, mock_llm):
        """LLM returns a name not in registry → Unknown."""
        mock_llm.return_value = '[{"index": 1, "speaker": "Karasuma Kaito", "confidence": 0.9}]'

        ch = _chapter(
            [
                _seg(0, SegmentType.NARRATION, "Someone spoke."),
                _seg(1, SegmentType.DIALOGUE, '"Hey."'),
                _seg(2, SegmentType.NARRATION, "The crowd murmured."),
            ]
        )

        result = attribute_chapter_per_dialogue(ch, REGISTRY)

        assert result.segments[1].speaker == "Unknown"
        assert result.segments[1].attribution_method == "fallback"
