"""Render aggregated runs to one self-contained, offline ``dashboard.html``.

Reuses the report package's Jinja2 environment shape (``PackageLoader`` +
``select_autoescape``). Run data is *never* interpolated through ``| safe``: it is
embedded as escaped JSON inside a ``<script type="application/json">`` block and
rendered into the DOM by vanilla JS via ``textContent``, so a hostile string in a
submitted leaderboard.json cannot break out of the script tag or inject markup
(plan §8 — the leaderboard accepts community submissions).
"""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from redharness.dashboard.aggregate import (
    SURFACE_ORDER,
    DashboardData,
    aggregate_runs,
)

_env = Environment(
    loader=PackageLoader("redharness.dashboard", "templates"),
    autoescape=select_autoescape(["html"]),
)

PROJECT_NAME = "redharness"

# Characters that must be escaped before embedding JSON in a <script> element:
# the angle brackets and ampersand that could terminate the element or open a
# tag, and the JS line/paragraph separators that are illegal in JS string
# literals (U+2028 / U+2029).
_SCRIPT_ESCAPES = {
    "&": "\\u0026",
    "<": "\\u003c",
    ">": "\\u003e",
    chr(0x2028): "\\u2028",
    chr(0x2029): "\\u2029",
}


def _safe_json(payload: object) -> str:
    """Serialize ``payload`` for safe embedding inside a ``<script>`` element."""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    for char, escape in _SCRIPT_ESCAPES.items():
        text = text.replace(char, escape)
    return text


def render_dashboard(data: DashboardData, generated_label: str | None = None) -> str:
    """Render the dashboard HTML from aggregated ``data``.

    ``generated_label`` is an optional caller-supplied label (e.g. a release tag).
    No wall-clock time is read, so output is deterministic for fixed inputs.
    """
    payload = {
        "project": PROJECT_NAME,
        "surfaceOrder": list(SURFACE_ORDER),
        "rows": [row.model_dump() for row in data.rows],
        "warnings": data.warnings,
        "summary": {
            "runs": data.run_count,
            "targets": data.target_count,
            "surfaces": data.surface_count,
            "cells": data.cell_count,
        },
    }
    template = _env.get_template("dashboard.html.j2")
    return template.render(
        project=PROJECT_NAME,
        generated_label=generated_label,
        data_json=_safe_json(payload),
    )


def write_dashboard(
    runs_dir: Path,
    out_path: Path,
    generated_label: str | None = None,
) -> DashboardData:
    """Aggregate ``runs_dir`` and write ``dashboard.html`` to ``out_path``.

    Returns the aggregated data so callers can surface warnings/counts.
    """
    data = aggregate_runs(runs_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_dashboard(data, generated_label))
    return data
