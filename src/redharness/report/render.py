"""Render a :class:`RunResult` to Markdown, HTML, and ``leaderboard.json``.

The leaderboard export is the canonical machine-readable artifact: a flat list of
rows, each tagging its number with the (dataset_version, judge, metric) triple so
results stay comparable and unambiguous across runs (plan §6).
"""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from redharness.runner.result import RunResult

_env = Environment(
    loader=PackageLoader("redharness.report", "templates"),
    autoescape=select_autoescape(["html"]),
)


def build_leaderboard(result: RunResult) -> list[dict]:
    """Flatten cells into leaderboard rows tagged with the full provenance triple."""
    rows: list[dict] = []
    for cell in result.cells:
        for metric_name, metric in cell.metrics.items():
            rows.append(
                {
                    "run_id": result.run_id,
                    "attack": cell.attack,
                    "target": cell.target,
                    "dataset": cell.dataset,
                    "dataset_version": cell.dataset_version,
                    "judge": cell.judge,
                    "metric": metric_name,
                    "value": metric.value,
                }
            )
    return rows


def render_markdown(result: RunResult) -> str:
    lines = [
        f"# redharness report — {result.run_name}",
        "",
        f"- run id: `{result.run_id}`",
        f"- seed: {result.seed}",
        f"- cells: {len(result.cells)}",
        "",
    ]
    for cell in result.cells:
        lines.append(f"## {cell.attack} × {cell.target}")
        lines.append("")
        lines.append(
            f"dataset `{cell.dataset}` ({cell.dataset_version}) · judge `{cell.judge}`"
        )
        lines.append("")
        lines.append("| metric | value |")
        lines.append("| --- | --- |")
        for name, metric in cell.metrics.items():
            lines.append(f"| {name} | {metric.value:.4f} |")
        lines.append("")
    return "\n".join(lines)


def render_html(result: RunResult) -> str:
    return _env.get_template("report.html.j2").render(result=result)


def write_reports(result: RunResult, out_dir: Path) -> dict[str, Path]:
    """Write report.md, report.html and leaderboard.json; return their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / "report.md"
    html_path = out_dir / "report.html"
    leaderboard_path = out_dir / "leaderboard.json"

    md_path.write_text(render_markdown(result))
    html_path.write_text(render_html(result))
    leaderboard_path.write_text(json.dumps(build_leaderboard(result), indent=2))

    return {"markdown": md_path, "html": html_path, "leaderboard": leaderboard_path}
