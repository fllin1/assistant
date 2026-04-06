"""Centralized configuration for model defaults and provider settings.

All model names and provider defaults live here so they can be changed
in one place without hunting through multiple modules.
"""

# -- Vision providers --

# Default provider when none is specified
DEFAULT_VISION_PROVIDER = "gemini"

# Default model per provider — used when --model is not passed
DEFAULT_MODELS = {
    "gemini": "gemini-flash-latest",
    "ollama": "qwen3-vl:8b",
}

# Ollama connection
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
