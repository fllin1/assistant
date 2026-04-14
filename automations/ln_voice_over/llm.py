"""Shared LLM utilities for the LN voice-over pipeline.

Wraps Ollama's chat API into a simple function used by both
the extraction and (future) attribution modules.
"""

from __future__ import annotations

from ollama import chat


def call_llm(system_prompt: str, user_prompt: str, model: str) -> str:
    """Send a system + user prompt to an Ollama model and return the response."""
    response = chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response["message"]["content"]
