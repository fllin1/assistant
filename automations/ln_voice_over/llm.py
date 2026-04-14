"""Shared LLM utilities for the LN voice-over pipeline.

Routes to Ollama (local) or OpenRouter (cloud) based on the model
registry in config.py. Pass the alias (e.g. "gemini-flash-lite")
or the full model ID (e.g. "gemma4:26b") — both are looked up.
"""

from __future__ import annotations

import os

from .config import MODEL_REGISTRY


def resolve_model(alias: str) -> tuple[str, str]:
    """Resolve a model alias to (provider, model_id).

    Raises ValueError if the alias is not in MODEL_REGISTRY.
    """
    entry = MODEL_REGISTRY.get(alias)
    if entry is None:
        known = ", ".join(sorted(MODEL_REGISTRY))
        raise ValueError(f"Unknown model '{alias}'. Known models: {known}")
    return entry


def call_llm(system_prompt: str, user_prompt: str, model: str) -> str:
    """Send a system + user prompt to an LLM and return the response."""
    provider, model_id = resolve_model(model)
    if provider == "openrouter":
        return _call_openrouter(system_prompt, user_prompt, model_id)
    return _call_ollama(system_prompt, user_prompt, model_id)


def _call_ollama(system_prompt: str, user_prompt: str, model_id: str) -> str:
    from ollama import chat

    response = chat(
        model=model_id,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response["message"]["content"]


def _call_openrouter(system_prompt: str, user_prompt: str, model_id: str) -> str:
    import openai

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY environment variable is not set")

    client = openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    return response.choices[0].message.content
