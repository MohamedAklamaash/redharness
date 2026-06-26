"""Multi-seed trials: aggregation math + an end-to-end deterministic equality lock."""

from __future__ import annotations

import json

import pytest

from redharness.config import RunConfig
from redharness.core.metric import MetricResult
from redharness.report import write_reports
from redharness.runner import Runner
from redharness.runner.result import CellResult, RunResult
from redharness.runner.trials import aggregate_trials, run_trials


def _config(trials: int = 1, run_name: str = "trialrun") -> RunConfig:
    return RunConfig.model_validate(
        {
            "run_name": run_name,
            "seed": 0,
            "trials": trials,
            "targets": [{"name": "reference"}],
            "attacks": [{"name": "static"}],
            "datasets": [{"name": "demo"}],
            "judges": [{"name": "refusal_match"}],
            "metrics": ["asr", "refusal_rate"],
        }
    )


def _cell(asr: float) -> CellResult:
    cell = CellResult(
        attack="static", target="reference", dataset="demo",
        dataset_version="demo@0", judge="refusal_match",
    )
    cell.metrics["asr"] = MetricResult(name="asr", value=asr)
    return cell


def test_aggregate_trials_means_and_bounds_value():
    cfg = _config()
    results = [
        RunResult(run_id="a", run_name="a", seed=0, cells=[_cell(0.2)], transcript_path="x"),
        RunResult(run_id="b", run_name="b", seed=1, cells=[_cell(0.4)], transcript_path="y"),
    ]
    aggregated = aggregate_trials(cfg, results)
    metric = aggregated.cells[0].metrics["asr"]
    assert metric.value == pytest.approx(0.3)
    assert 0.2 <= metric.ci_low <= metric.ci_high <= 0.4
    assert metric.breakdown["trial_values"] == [0.2, 0.4]


def test_aggregate_trials_handles_all_na():
    cfg = _config()
    na_cell = CellResult(
        attack="static", target="reference", dataset="demo",
        dataset_version="demo@0", judge="refusal_match",
    )
    na_cell.metrics["asr"] = MetricResult(name="asr", value=None)
    results = [
        RunResult(run_id="a", run_name="a", seed=0, cells=[na_cell], transcript_path="x"),
    ]
    metric = aggregate_trials(cfg, results).cells[0].metrics["asr"]
    assert metric.value is None
    assert metric.ci_low is None


def test_run_trials_deterministic_targets_give_zero_width_ci(tmp_path):
    aggregated, run_dir = run_trials(_config(trials=3), tmp_path)
    assert run_dir.name == "trialrun"
    # Reference targets are seed-independent, so every trial is identical: the mean
    # equals the single value and the bootstrap interval has width zero.
    for cell in aggregated.cells:
        for metric in cell.metrics.values():
            assert metric.ci_low == metric.value
            assert metric.ci_high == metric.value


def test_run_trials_matches_single_run_values(tmp_path):
    single = Runner(_config(trials=1, run_name="single"), tmp_path / "s").run()
    aggregated, _ = run_trials(_config(trials=4, run_name="single"), tmp_path / "m")
    single_by = {
        (c.target, c.attack, c.judge): c.metrics["asr"].value for c in single.cells
    }
    multi_by = {
        (c.target, c.attack, c.judge): c.metrics["asr"].value for c in aggregated.cells
    }
    assert single_by == multi_by


def test_run_trials_writes_per_trial_artifacts(tmp_path):
    aggregated, run_dir = run_trials(_config(trials=2), tmp_path)
    paths = write_reports(aggregated, run_dir)
    rows = json.loads(paths["leaderboard"].read_text())
    assert any(r["metric"] == "asr" for r in rows)
    # Both trial sub-runs are kept on disk.
    assert (run_dir / "trials" / "trialrun-trial-0").is_dir()
    assert (run_dir / "trials" / "trialrun-trial-1").is_dir()
