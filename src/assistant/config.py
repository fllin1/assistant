"""Centralized configuration for assistant defaults.

Defaults live here so they can be changed in one place without hunting
through multiple modules.
"""

# -- Interaction defaults --

DEFAULT_TEXT_PROVIDER = "openrouter"
DEFAULT_TEXT_MODEL = "deepseek/deepseek-v4-pro"

# Default monitor: 0 is the combined virtual desktop, 1 is the primary monitor.
DEFAULT_MONITOR = 1
