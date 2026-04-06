"""Tests for the vision module."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from PIL import Image

from assistant.vision import (
    VisionResponse,
    _format_history,
    _parse_response,
    analyze_screenshot,
)

# -- _parse_response --


def test_parse_valid_json():
    raw = json.dumps(
        {
            "reasoning": "I see a search bar",
            "action": "left_click",
            "target": "B3",
            "text": None,
            "confidence": "high",
        }
    )
    result = _parse_response(raw)

    assert isinstance(result, VisionResponse)
    assert result.action == "left_click"
    assert result.target == "B3"
    assert result.confidence == "high"


def test_parse_json_with_code_fences():
    raw = (
        "```json\n"
        '{"reasoning": "test", "action": "done", "target": null,'
        ' "text": null, "confidence": "high"}\n'
        "```"
    )
    result = _parse_response(raw)

    assert result.action == "done"
    assert result.target is None


def test_parse_json_with_bare_fences():
    raw = (
        "```\n"
        '{"reasoning": "test", "action": "type", "target": null,'
        ' "text": "hello", "confidence": "medium"}\n'
        "```"
    )
    result = _parse_response(raw)

    assert result.action == "type"
    assert result.text == "hello"


def test_parse_invalid_json():
    result = _parse_response("this is not json at all")

    assert result.action == "error"
    assert "Parse error" in result.reasoning


def test_parse_unknown_action():
    raw = json.dumps(
        {
            "reasoning": "test",
            "action": "explode",
            "target": None,
            "text": None,
            "confidence": "high",
        }
    )
    result = _parse_response(raw)

    assert result.action == "error"


def test_parse_missing_fields_uses_defaults():
    raw = json.dumps({"reasoning": "minimal", "action": "done"})
    result = _parse_response(raw)

    assert result.action == "done"
    assert result.target is None
    assert result.text is None
    assert result.confidence == "medium"


# -- _format_history --


def test_format_history_empty():
    result = _format_history([])
    assert "Previous actions:" in result


def test_format_history_with_steps():
    history = [
        {"action": "left_click", "target": "B3", "reasoning": "Clicked search"},
        {"action": "type", "target": None, "reasoning": "Typed query"},
    ]
    result = _format_history(history)

    assert "Step 1:" in result
    assert "Step 2:" in result
    assert "left_click" in result
    assert "Typed query" in result


# -- analyze_screenshot: Gemini --


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    img = Image.new("RGB", (100, 100))
    with pytest.raises(ValueError, match="No API key found"):
        analyze_screenshot(img, task="test")


def test_unknown_provider_raises():
    img = Image.new("RGB", (100, 100))
    with pytest.raises(ValueError, match="Unknown vision provider"):
        analyze_screenshot(img, task="test", provider="openai")


@patch("assistant.vision._analyze_gemini")
def test_analyze_screenshot_calls_gemini(mock_gemini):
    mock_gemini.return_value = VisionResponse(
        reasoning="test",
        action="done",
        target=None,
        text=None,
        confidence="high",
    )

    img = Image.new("RGB", (1024, 768))
    result = analyze_screenshot(img, task="test task")

    assert result.action == "done"
    mock_gemini.assert_called_once()


# -- analyze_screenshot: Ollama --


@patch("assistant.vision._analyze_ollama")
def test_analyze_screenshot_calls_ollama(mock_ollama):
    mock_ollama.return_value = VisionResponse(
        reasoning="test",
        action="done",
        target=None,
        text=None,
        confidence="high",
    )

    img = Image.new("RGB", (1024, 768))
    result = analyze_screenshot(img, task="test task", provider="ollama")

    assert result.action == "done"
    mock_ollama.assert_called_once()


@patch("assistant.vision._analyze_ollama")
def test_analyze_screenshot_passes_model(mock_ollama):
    mock_ollama.return_value = VisionResponse(
        reasoning="test",
        action="done",
        target=None,
        text=None,
        confidence="high",
    )

    img = Image.new("RGB", (1024, 768))
    analyze_screenshot(img, task="test", provider="ollama", model="llava:13b")

    # model should be passed through to the provider
    call_kwargs = mock_ollama.call_args
    assert call_kwargs[1]["model"] == "llava:13b"


# -- _analyze_ollama --


@patch("httpx.post")
def test_analyze_ollama_success(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {
            "content": json.dumps(
                {
                    "reasoning": "I see a button",
                    "action": "left_click",
                    "target": "C4",
                    "text": None,
                    "confidence": "high",
                }
            )
        }
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    from assistant.vision import _analyze_ollama

    result = _analyze_ollama(b"fake-png-bytes", "test prompt")

    assert result.action == "left_click"
    assert result.target == "C4"
    mock_post.assert_called_once()
    # Verify model default
    assert mock_post.call_args.kwargs["json"]["model"] == "qwen3-vl:8b"


@patch("httpx.post", side_effect=httpx.ConnectError("refused"))
def test_analyze_ollama_connection_refused(mock_post):
    from assistant.vision import _analyze_ollama

    with pytest.raises(ConnectionError, match="Cannot connect to Ollama"):
        _analyze_ollama(b"fake-png-bytes", "test prompt")


@patch("httpx.post")
def test_analyze_ollama_custom_host(mock_post, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://my-server:11434")
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {
            "content": json.dumps(
                {
                    "reasoning": "test",
                    "action": "done",
                    "target": None,
                    "text": None,
                    "confidence": "high",
                }
            )
        }
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    from assistant.vision import _analyze_ollama

    _analyze_ollama(b"fake-png-bytes", "test prompt")

    call_url = mock_post.call_args[0][0]
    assert call_url == "http://my-server:11434/api/chat"
