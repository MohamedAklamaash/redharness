"""Renderer and CLI e2e tests: self-containment, XSS-safety, determinism, N/A."""

from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from redharness.cli import app
from redharness.dashboard import aggregate_runs, render_dashboard
from redharness.dashboard.render import _safe_json

runner = CliRunner()
_CONFIGS = Path(__file__).resolve().parents[1] / "configs"
SMOKE_CONFIG = _CONFIGS / "smoke.yaml"

XSS_PAYLOAD = "</script><img src=x onerror=alert(1)>"

# Matches a <script src=...> or <link href=...> pointing at an external host.
_EXTERNAL_RESOURCE = re.compile(
    r"<(?:script[^>]+src|link[^>]+href)\s*=\s*['\"]?https?://", re.IGNORECASE
)


def _row(metric: str, value, **over) -> dict:
    base = {
        "run_id": "r1",
        "attack": "static",
        "target": "mock",
        "dataset": "demo",
        "dataset_version": "demo@abc",
        "judge": "refusal_match",
        "metric": metric,
        "value": value,
    }
    base.update(over)
    return base


def _write_leaderboard(runs_dir: Path, run_id: str, rows: list[dict]) -> None:
    run = runs_dir / run_id
    run.mkdir(parents=True)
    (run / "leaderboard.json").write_text(json.dumps(rows))


def test_run_then_dashboard_creates_file(tmp_path):
    runs = tmp_path / "runs"
    assert runner.invoke(app, ["run", str(SMOKE_CONFIG), "--runs-dir", str(runs)]).exit_code == 0
    out = tmp_path / "dashboard.html"

    result = runner.invoke(app, ["dashboard", "--runs-dir", str(runs), "--out", str(out)])

    assert result.exit_code == 0
    assert out.exists()
    assert "dashboard written" in result.stdout
    html = out.read_text()
    assert '<script type="application/json" id="data">' in html


def test_dashboard_is_self_contained_no_external_resources(tmp_path):
    runs = tmp_path / "runs"
    runner.invoke(app, ["run", str(SMOKE_CONFIG), "--runs-dir", str(runs)])
    out = tmp_path / "dashboard.html"
    runner.invoke(app, ["dashboard", "--runs-dir", str(runs), "--out", str(out)])

    html = out.read_text()
    assert not _EXTERNAL_RESOURCE.search(html), "dashboard pulls an external resource"
    assert "http://" not in html and "https://" not in html


def test_na_rendered_as_em_dash(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(runs, "smoke", [_row("asr", None)])
    html = render_dashboard(aggregate_runs(runs))
    # The value is N/A in the data and the JS renders it as an em dash; the glyph
    # is present in the template's client-side rendering path.
    data_block = _data_payload(html)
    assert data_block["rows"][0]["value"] is None
    assert "—" in html


def test_xss_payload_not_present_unescaped(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(
        runs, "smoke", [_row("asr", 0.0, target=XSS_PAYLOAD, attack=XSS_PAYLOAD)]
    )
    html = render_dashboard(aggregate_runs(runs))

    # The literal closing-script + img tag must never appear verbatim: it would
    # break out of the <script> block or inject markup.
    assert XSS_PAYLOAD not in html
    assert "</script><img" not in html
    # The angle brackets must be neutralized into their escaped form so the
    # payload cannot terminate the script element or open a tag.
    assert "\\u003c/script\\u003e" in html
    # And the data still round-trips back to the original payload from the island.
    payload = _data_payload(html)
    assert payload["rows"][0]["target"] == XSS_PAYLOAD


def test_dashboard_generation_is_byte_identical(tmp_path):
    runs = tmp_path / "runs"
    runner.invoke(app, ["run", str(SMOKE_CONFIG), "--runs-dir", str(runs)])
    first = tmp_path / "a.html"
    second = tmp_path / "b.html"
    runner.invoke(app, ["dashboard", "--runs-dir", str(runs), "--out", str(first)])
    runner.invoke(app, ["dashboard", "--runs-dir", str(runs), "--out", str(second)])

    assert first.read_bytes() == second.read_bytes()


def test_empty_runs_dir_friendly_state(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    out = tmp_path / "dashboard.html"
    result = runner.invoke(app, ["dashboard", "--runs-dir", str(runs), "--out", str(out)])

    assert result.exit_code == 0
    html = out.read_text()
    assert "No runs yet" in html


def test_missing_runs_dir_is_not_an_error(tmp_path):
    out = tmp_path / "dashboard.html"
    result = runner.invoke(
        app, ["dashboard", "--runs-dir", str(tmp_path / "nope"), "--out", str(out)]
    )
    assert result.exit_code == 0
    assert out.exists()


def test_runs_path_not_a_directory_exits_nonzero(tmp_path):
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x")
    result = runner.invoke(
        app, ["dashboard", "--runs-dir", str(not_a_dir), "--out", str(tmp_path / "d.html")]
    )
    assert result.exit_code == 1


def test_malformed_leaderboard_reported_to_stderr(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(runs, "good", [_row("asr", 0.0)])
    (runs / "bad").mkdir()
    (runs / "bad" / "leaderboard.json").write_text("not json")
    out = tmp_path / "dashboard.html"

    result = runner.invoke(app, ["dashboard", "--runs-dir", str(runs), "--out", str(out)])

    assert result.exit_code == 0
    assert "skipped" in result.stdout + result.stderr
    assert "1 metric cell" in result.stdout


def test_generated_label_optional_and_omitted_by_default(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(runs, "smoke", [_row("asr", 0.0)])
    without = render_dashboard(aggregate_runs(runs))
    with_label = render_dashboard(aggregate_runs(runs), generated_label="benchmark-v1")

    assert "Generated:" not in without
    assert "Generated: benchmark-v1" in with_label


def test_safe_json_escapes_separators():
    # U+2028 / U+2029 are illegal in JS string literals and must be escaped.
    out = _safe_json({"x": f"a{chr(0x2028)}b{chr(0x2029)}c"})
    assert chr(0x2028) not in out
    assert chr(0x2029) not in out
    assert "\\u2028" in out and "\\u2029" in out


def _data_payload(html: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="data">(.*?)</script>', html, re.DOTALL
    )
    assert match, "embedded JSON data block not found"
    raw = (
        match.group(1)
        .replace("\\u0026", "&")
        .replace("\\u003c", "<")
        .replace("\\u003e", ">")
        .replace("\\u2028", chr(0x2028))
        .replace("\\u2029", chr(0x2029))
    )
    return json.loads(raw)
