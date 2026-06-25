"""Golden tests for the dashboard aggregator (surface mapping, N/A, malformed input)."""

from __future__ import annotations

import json
from pathlib import Path

from redharness.dashboard.aggregate import aggregate_runs, surface_for_metric


def _write_leaderboard(runs_dir: Path, run_id: str, rows: list[dict]) -> None:
    run = runs_dir / run_id
    run.mkdir(parents=True)
    (run / "leaderboard.json").write_text(json.dumps(rows))


def _row(metric: str, value, **over) -> dict:
    base = {
        "run_id": "r1",
        "attack": "static",
        "target": "reference",
        "dataset": "demo",
        "dataset_version": "demo@abc",
        "judge": "refusal_match",
        "metric": metric,
        "value": value,
    }
    base.update(over)
    return base


def test_surface_for_metric_covers_three_surfaces_and_other():
    assert surface_for_metric("asr") == "jailbreak"
    assert surface_for_metric("frr") == "jailbreak"
    assert surface_for_metric("injection_success_rate") == "injection"
    assert surface_for_metric("utility_baseline") == "injection"
    assert surface_for_metric("extraction_rate") == "leakage"
    assert surface_for_metric("verbatim_overlap") == "leakage"
    assert surface_for_metric("totally_made_up") == "other"


def test_missing_runs_dir_is_empty_not_error(tmp_path):
    data = aggregate_runs(tmp_path / "does_not_exist")
    assert data.rows == []
    assert data.warnings == []


def test_empty_runs_dir_is_empty(tmp_path):
    (tmp_path / "runs").mkdir()
    data = aggregate_runs(tmp_path / "runs")
    assert data.rows == []
    assert data.cell_count == 0


def test_combines_rows_and_tags_surface(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(
        runs, "smoke", [_row("asr", 0.0), _row("injection_success_rate", 0.5)]
    )
    _write_leaderboard(runs, "leak", [_row("extraction_rate", 0.25, run_id="r2")])

    data = aggregate_runs(runs)

    assert data.cell_count == 3
    by_metric = {r.metric: r for r in data.rows}
    assert by_metric["asr"].surface == "jailbreak"
    assert by_metric["injection_success_rate"].surface == "injection"
    assert by_metric["extraction_rate"].surface == "leakage"
    assert data.run_count == 2


def test_null_value_preserved_as_na(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(runs, "smoke", [_row("asr", None)])
    data = aggregate_runs(runs)
    assert data.rows[0].value is None


def test_unknown_metric_maps_to_other(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(runs, "smoke", [_row("brand_new_metric", 0.1)])
    data = aggregate_runs(runs)
    assert data.rows[0].surface == "other"
    assert data.rows[0].is_rate is False


def test_rate_metric_flagged(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(runs, "smoke", [_row("asr", 0.3)])
    data = aggregate_runs(runs)
    assert data.rows[0].is_rate is True


def test_non_numeric_values_coerced_to_na(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(
        runs,
        "smoke",
        [_row("asr", True), _row("refusal_rate", "oops", run_id="r2")],
    )
    data = aggregate_runs(runs)
    # A bool (int subclass) and an unparsable string both become N/A, not a number.
    assert all(row.value is None for row in data.rows)


def test_malformed_file_skipped_with_warning_others_aggregated(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(runs, "good", [_row("asr", 0.0)])
    bad = runs / "bad"
    bad.mkdir()
    (bad / "leaderboard.json").write_text("{ this is not json")

    data = aggregate_runs(runs)

    assert data.cell_count == 1
    assert data.rows[0].metric == "asr"
    assert len(data.warnings) == 1
    assert "bad" in data.warnings[0]


def test_missing_required_field_skips_file(tmp_path):
    runs = tmp_path / "runs"
    partial = runs / "partial"
    partial.mkdir(parents=True)
    (partial / "leaderboard.json").write_text(json.dumps([{"run_id": "x", "metric": "asr"}]))

    data = aggregate_runs(runs)

    assert data.cell_count == 0
    assert len(data.warnings) == 1
    assert "missing required fields" in data.warnings[0]


def test_non_list_payload_skipped(tmp_path):
    runs = tmp_path / "runs"
    obj = runs / "obj"
    obj.mkdir(parents=True)
    (obj / "leaderboard.json").write_text(json.dumps({"not": "a list"}))

    data = aggregate_runs(runs)

    assert data.cell_count == 0
    assert "expected a list" in data.warnings[0]


def test_deterministic_row_order(tmp_path):
    runs = tmp_path / "runs"
    _write_leaderboard(
        runs,
        "smoke",
        [
            _row("verbatim_overlap", 0.1, target="zeta"),
            _row("asr", 0.2, target="alpha"),
            _row("injection_success_rate", 0.3, target="beta"),
        ],
    )
    first = [r.surface for r in aggregate_runs(runs).rows]
    second = [r.surface for r in aggregate_runs(runs).rows]
    assert first == second
    # jailbreak sorts before injection before leakage.
    assert first == ["jailbreak", "injection", "leakage"]
