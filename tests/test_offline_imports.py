"""The zero-extras tripwire: the offline core must import no heavy ML/cloud deps.

``plugins.py`` eagerly imports every plugin submodule at core load, so a single
module-level ``import torch`` in any plugin would break ``import redharness`` for
everyone and silently bloat the offline core. This test fails loudly if that ever
happens: it imports the whole plugin surface in a fresh interpreter and asserts none
of the heavy modules are present in ``sys.modules`` afterwards. CI runs it on the
base ``.[dev]`` install (which has none of these extras).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from redharness.cli import app

REPO_ROOT = Path(__file__).resolve().parents[1]

HEAVY_MODULES = {"torch", "transformers", "boto3", "vllm", "garak", "pyrit"}


def test_importing_plugins_pulls_in_no_heavy_dependency():
    script = (
        "import sys\n"
        "import redharness.plugins\n"
        f"heavy = {sorted(HEAVY_MODULES)!r}\n"
        "present = sorted(set(heavy) & set(sys.modules))\n"
        "assert not present, f'offline core imported heavy deps: {present}'\n"
        "print('OFFLINE_IMPORTS_OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OFFLINE_IMPORTS_OK" in proc.stdout


def test_no_heavy_module_in_sys_modules_after_import():
    import redharness.plugins  # noqa: F401

    assert HEAVY_MODULES & set(sys.modules) == set()


def test_redharness_list_works_offline():
    result = CliRunner().invoke(app, ["list"])
    assert result.exit_code == 0
    assert "targets:" in result.stdout
    assert "tap" in result.stdout
    assert "crescendo" in result.stdout
