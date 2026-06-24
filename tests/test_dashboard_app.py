"""Tests for the dashboard app's pure data-shaping helpers and the CLI launch path.

The helpers run without launching a server. pandas-backed helpers are guarded with
``pytest.importorskip`` so the suite passes whether or not the optional ``dashboard``
extra is installed. The CLI test asserts the command's contract (help text, no server
launch in tests).
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from redharness.cli import app
from redharness.dashboard.app import (
    NA_DISPLAY,
    filter_rows,
    format_value,
    load_data,
    present_surfaces,
    rows_for_surface,
)

runner = CliRunner()


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


# --- pure helpers (no streamlit / pandas required) -------------------------------


def test_load_data_groups_rows_by_surface(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(
        runs,
        "smoke",
        [_row("asr", 0.2), _row("injection_success_rate", 0.5)],
    )
    _write_leaderboard(runs, "leak", [_row("extraction_rate", 0.1, run_id="r2")])

    data = load_data(runs)

    assert present_surfaces(data) == ["jailbreak", "injection", "leakage"]
    assert [r.metric for r in rows_for_surface(data, "jailbreak")] == ["asr"]
    assert [r.metric for r in rows_for_surface(data, "leakage")] == ["extraction_rate"]


def test_unknown_metric_groups_under_other(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(runs, "smoke", [_row("brand_new_metric", 0.1)])
    data = load_data(runs)
    assert present_surfaces(data) == ["other"]
    assert rows_for_surface(data, "other")[0].metric == "brand_new_metric"


def test_empty_runs_dir_yields_no_surfaces(tmp_path):
    (tmp_path / "runs").mkdir()
    data = load_data(tmp_path / "runs")
    assert data.rows == []
    assert present_surfaces(data) == []


def test_missing_runs_dir_is_empty_not_error(tmp_path):
    data = load_data(tmp_path / "nope")
    assert data.rows == []


def test_format_value_renders_na_as_em_dash():
    assert format_value(None) == NA_DISPLAY
    assert format_value(0.5) == "0.500"


def test_filter_rows_by_surface_target_metric_and_search(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(
        runs,
        "smoke",
        [
            _row("asr", 0.2, target="alpha", attack="gcg"),
            _row("refusal_rate", 0.8, target="beta", attack="pair"),
            _row("extraction_rate", 0.1, target="alpha", attack="divergence"),
        ],
    )
    rows = load_data(runs).rows

    assert {r.target for r in filter_rows(rows, targets=["alpha"])} == {"alpha"}
    assert {r.metric for r in filter_rows(rows, surfaces=["jailbreak"])} == {
        "asr",
        "refusal_rate",
    }
    assert [r.metric for r in filter_rows(rows, metrics=["asr"])] == ["asr"]
    assert [r.attack for r in filter_rows(rows, attack_query="GCG")] == ["gcg"]
    assert [r.target for r in filter_rows(rows, search="divergence")] == ["alpha"]
    # No filters => all rows pass through.
    assert filter_rows(rows) == rows


def test_malformed_file_skipped_with_warning(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(runs, "good", [_row("asr", 0.0)])
    (runs / "bad").mkdir()
    (runs / "bad" / "leaderboard.json").write_text("not json")

    data = load_data(runs)

    assert data.cell_count == 1
    assert len(data.warnings) == 1


# --- pandas-backed frame helpers (optional extra) --------------------------------


def test_build_frame_formats_na_and_orders_columns(tmp_path):
    import pytest

    pytest.importorskip("pandas")
    from redharness.dashboard.app import TABLE_COLUMNS, build_frame

    runs = tmp_path / "runs"
    _write_leaderboard(runs, "smoke", [_row("asr", None), _row("refusal_rate", 0.5)])
    rows = load_data(runs).rows

    frame = build_frame(rows)

    assert list(frame.columns) == list(TABLE_COLUMNS)
    values = frame["value"].tolist()
    assert NA_DISPLAY in values
    assert "0.500" in values


def test_build_rate_chart_frame_drops_na_and_pivots(tmp_path):
    import pytest

    pytest.importorskip("pandas")
    from redharness.dashboard.app import build_rate_chart_frame

    runs = tmp_path / "runs"
    _write_leaderboard(
        runs,
        "smoke",
        [
            _row("asr", 0.2, target="alpha"),
            _row("asr", 0.4, target="beta"),
            _row("refusal_rate", None, target="alpha"),
        ],
    )
    rows = load_data(runs).rows

    chart = build_rate_chart_frame(rows)

    assert "asr" in chart.columns
    assert set(chart.index) == {"alpha", "beta"}
    # The N/A refusal_rate cell must not appear as a value.
    assert chart["asr"].loc["alpha"] == 0.2


def test_build_rate_chart_frame_empty_when_no_rate_cells(tmp_path):
    import pytest

    pytest.importorskip("pandas")
    from redharness.dashboard.app import build_rate_chart_frame

    runs = tmp_path / "runs"
    _write_leaderboard(runs, "smoke", [_row("brand_new_metric", 0.1)])
    rows = load_data(runs).rows
    assert build_rate_chart_frame(rows).empty


# --- CLI contract (no server launch) ---------------------------------------------


def test_dashboard_help_documents_streamlit_and_options():
    result = runner.invoke(app, ["dashboard", "--help"])
    assert result.exit_code == 0
    out = result.stdout
    assert "--runs-dir" in out
    assert "--port" in out
    assert "--out" not in out  # the old HTML option is gone
    assert "--label" not in out


def test_dashboard_rejects_non_directory_runs_path(tmp_path):
    from redharness.errors import DashboardError

    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x")
    result = runner.invoke(app, ["dashboard", "--runs-dir", str(not_a_dir)])
    assert result.exit_code == 1
    assert isinstance(result.exception, DashboardError)
    assert "not a directory" in str(result.exception)


def test_launch_dashboard_errors_clearly_when_streamlit_missing(tmp_path, monkeypatch):
    from redharness.dashboard import launch
    from redharness.errors import DashboardError

    monkeypatch.setattr(launch, "_streamlit_available", lambda: False)
    runs = tmp_path / "runs"
    runs.mkdir()
    try:
        launch.launch_dashboard(runs, 8501)
    except DashboardError as exc:
        assert "uv pip install -e '.[dashboard]'" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected DashboardError when streamlit is missing")


def test_launch_dashboard_invokes_streamlit_with_runs_dir(tmp_path, monkeypatch):
    import subprocess
    import sys

    from redharness.dashboard import launch
    from redharness.dashboard.app import RUNS_DIR_ENV

    monkeypatch.setattr(launch, "_streamlit_available", lambda: True)
    captured: dict = {}

    def fake_run(command, env, check):
        captured["command"] = command
        captured["env"] = env
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(launch.subprocess, "run", fake_run)
    runs = tmp_path / "runs"
    runs.mkdir()

    code = launch.launch_dashboard(runs, 8502)

    assert code == 0
    cmd = captured["command"]
    assert cmd[:3] == [sys.executable, "-m", "streamlit"]
    assert str(launch.app_path()) in cmd
    assert "8502" in cmd
    assert cmd[-2:] == ["--runs-dir", str(runs)]
    assert captured["env"][RUNS_DIR_ENV] == str(runs)


def test_app_path_points_at_app_module():
    from redharness.dashboard import launch

    assert launch.app_path().name == "app.py"
    assert launch.app_path().is_file()
