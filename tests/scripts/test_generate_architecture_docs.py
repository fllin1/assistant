"""Tests for the architecture fact generator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_generator_handles_generic_prefix_and_package_imports(tmp_path: Path) -> None:
    source = tmp_path / "example_pkg"
    tests = tmp_path / "tests"
    output = tmp_path / "out"
    source.mkdir()
    tests.mkdir()

    (source / "__init__.py").write_text('"""Example package."""\n', encoding="utf-8")
    (source / "alpha.py").write_text(
        '"""Alpha module."""\n\ndef do_alpha() -> int:\n    return 1\n',
        encoding="utf-8",
    )
    (source / "beta.py").write_text(
        '"""Beta module."""\n\n'
        "from . import alpha\n\n"
        "def do_beta() -> int:\n"
        "    return alpha.do_alpha()\n",
        encoding="utf-8",
    )
    (tests / "test_alpha.py").write_text(
        "from example_pkg import alpha\n\n"
        "def test_do_alpha() -> None:\n"
        "    assert alpha.do_alpha() == 1\n",
        encoding="utf-8",
    )

    script = Path.cwd() / "scripts" / "generate_architecture_docs.py"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--source",
            str(source),
            "--tests",
            str(tests),
            "--output",
            str(output),
            "--module-prefix",
            "example_pkg",
            "--name",
            "example",
        ],
        check=True,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    imports = (output / "example-imports.mmd").read_text(encoding="utf-8")
    test_map = (output / "example-test-map.md").read_text(encoding="utf-8")

    assert '["alpha"]' in imports
    assert '["beta"]' in imports
    assert "| `example_pkg` | _No direct test found_ |" in test_map
    assert "| `example_pkg.alpha` | `tests/test_alpha.py` |" in test_map
