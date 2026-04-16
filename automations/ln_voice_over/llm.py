"""LLM client for the LN voice-over pipeline.

Provides LLMClient, a reusable wrapper that creates the provider connection
once and exposes a chat() method. Supports Ollama (local) and OpenRouter
(cloud via OpenAI-compatible API).

Usage:
    client = LLMClient("gemini-flash")
    response = client.chat(system_prompt, user_prompt)
"""

from __future__ import annotations

import logging
import os

from .config import MODEL_REGISTRY

logger = logging.getLogger(__name__)


def resolve_model(alias: str) -> tuple[str, str]:
    """Resolve a model alias to (provider, model_id).

    Raises ValueError if the alias is not in MODEL_REGISTRY.
    """
    entry = MODEL_REGISTRY.get(alias)
    if entry is None:
        known = ", ".join(sorted(MODEL_REGISTRY))
        raise ValueError(f"Unknown model '{alias}'. Known models: {known}")
    return entry


class LLMClient:
    """Reusable LLM client. Creates provider connection once.

    For OpenRouter, the openai.OpenAI client is created eagerly in __init__
    and reused across all chat() calls (connection pooling).
    For Ollama, the library is stateless so no client is held.
    """

    def __init__(self, model_alias: str, temperature: float = 0.0) -> None:
        self.provider, self.model_id = resolve_model(model_alias)
        self.model_alias = model_alias
        self.temperature = temperature

        if self.provider == "openrouter":
            import openai

            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError("OPENROUTER_API_KEY environment variable is not set")
            self._openrouter_client = openai.OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a system + user prompt and return the response text."""
        if self.provider == "openrouter":
            return self._chat_openrouter(system_prompt, user_prompt)
        return self._chat_ollama(system_prompt, user_prompt)

    def _chat_ollama(self, system_prompt: str, user_prompt: str) -> str:
        from ollama import chat

        response = chat(
            model=self.model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response["message"]["content"]

    def _chat_openrouter(self, system_prompt: str, user_prompt: str) -> str:
        response = self._openrouter_client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
        )
        return response.choices[0].message.content
