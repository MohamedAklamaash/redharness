"""Launch the Streamlit dashboard app as a subprocess.

Streamlit is an optional extra (``.[dashboard]``): if it is not installed we raise a
typed :class:`DashboardError` telling the user how to install it, rather than crashing
with a bare ``ModuleNotFoundError``. The app module path is resolved from this package
so it works from an installed wheel, and Streamlit is invoked via
``sys.executable -m streamlit`` so we never hardcode a binary path.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from redharness.dashboard import app as _app_module
from redharness.errors import DashboardError

_INSTALL_HINT = "uv pip install -e '.[dashboard]'"


def app_path() -> Path:
    """Absolute path to the Streamlit app module."""
    return Path(_app_module.__file__).resolve()


def _streamlit_available() -> bool:
    return importlib.util.find_spec("streamlit") is not None


def launch_dashboard(runs_dir: Path, port: int) -> int:
    """Run ``streamlit run app.py`` for ``runs_dir`` on ``port``.

    Returns the subprocess exit code. Raises :class:`DashboardError` if Streamlit is
    not installed (the ``dashboard`` extra was not installed).
    """
    if not _streamlit_available():
        raise DashboardError(
            "the dashboard requires Streamlit, which is not installed. "
            f"Install the optional extra with: {_INSTALL_HINT}"
        )

    env = dict(os.environ)
    env[_app_module.RUNS_DIR_ENV] = str(runs_dir)

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path()),
        "--server.port",
        str(port),
        "--",
        "--runs-dir",
        str(runs_dir),
    ]
    completed = subprocess.run(command, env=env, check=False)
    return completed.returncode
