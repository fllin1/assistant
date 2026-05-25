"""Import checks for the LNVO v2 skeleton."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "automations.ln_voice_over_v2",
        "automations.ln_voice_over_v2.common.artifacts",
        "automations.ln_voice_over_v2.common.enums",
        "automations.ln_voice_over_v2.common.errors",
        "automations.ln_voice_over_v2.common.ids",
        "automations.ln_voice_over_v2.common.json_io",
        "automations.ln_voice_over_v2.common.paths",
        "automations.ln_voice_over_v2.series.contracts",
        "automations.ln_voice_over_v2.pipeline.contracts",
        "automations.ln_voice_over_v2.pipeline.validators",
        "automations.ln_voice_over_v2.stages.prepare.contracts",
        "automations.ln_voice_over_v2.stages.transform.contracts",
        "automations.ln_voice_over_v2.stages.dialogue.contracts",
        "automations.ln_voice_over_v2.stages.scenes.contracts",
        "automations.ln_voice_over_v2.stages.generation.contracts",
    ],
)
def test_lnvo_v2_modules_import(module_name: str) -> None:
    """All planned skeleton modules are importable."""
    importlib.import_module(module_name)
