"""End-to-end leakage smoke test: run configs/leakage_smoke.yaml offline."""

from __future__ import annotations

import json
from pathlib import Path

from redharness.config import load_config
from redharness.report import write_reports
from redharness.runner import Runner

SMOKE_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "leakage_smoke.yaml"

_LEAKAGE_METRICS = {
    "extraction_rate",
    "canary_exposure_rate",
    "pii_leak_rate",
    "system_prompt_leak_rate",
    "verbatim_overlap",
}


def _run(tmp_path):
    cfg = load_config(SMOKE_CONFIG)
    runner = Runner(cfg, tmp_path)
    result = runner.run()
    paths = write_reports(result, runner.run_dir)
    return result, paths


def test_leakage_smoke_produces_artifacts(tmp_path):
    result, paths = _run(tmp_path)
    assert Path(result.transcript_path).exists()
    assert paths["markdown"].exists()
    assert paths["html"].exists()
    assert paths["leaderboard"].exists()
    # 2 targets x 5 attacks x 1 dataset x 1 judge = 10 cells.
    assert len(result.cells) == 10


def test_leakage_smoke_leaky_vs_guarded(tmp_path):
    result, _ = _run(tmp_path)
    by_cell = {(c.target, c.attack): c for c in result.cells}

    # The guarded model leaks nothing: every leak-rate metric is 0 for every attack.
    for attack in (
        "direct_extraction",
        "divergence",
        "canary_completion",
        "system_prompt_leak",
        "pii_elicitation",
    ):
        guarded = by_cell[("model_guarded", attack)]
        assert guarded.metrics["extraction_rate"].value == 0.0
        assert guarded.metrics["canary_exposure_rate"].value == 0.0
        assert guarded.metrics["pii_leak_rate"].value == 0.0
        assert guarded.metrics["system_prompt_leak_rate"].value == 0.0

    # The leaky model leaks: the system_prompt_leak attack (which plants the hidden
    # prompt in context) fully exfiltrates every category it touches.
    leaky_sysprompt = by_cell[("model_leaky", "system_prompt_leak")]
    assert leaky_sysprompt.metrics["system_prompt_leak_rate"].value == 1.0
    assert leaky_sysprompt.metrics["extraction_rate"].value == 1.0
    assert leaky_sysprompt.metrics["verbatim_overlap"].value == 1.0

    # Canary probes are recovered by the leaky model under every attack framing.
    for attack in ("direct_extraction", "canary_completion"):
        cell = by_cell[("model_leaky", attack)]
        assert cell.metrics["canary_exposure_rate"].value == 1.0

    # The leaky model strictly out-leaks the guarded one overall.
    for attack in ("direct_extraction", "canary_completion", "system_prompt_leak"):
        leaky = by_cell[("model_leaky", attack)].metrics["extraction_rate"].value
        guarded = by_cell[("model_guarded", attack)].metrics["extraction_rate"].value
        assert leaky > guarded


def test_leakage_smoke_leaderboard_provenance_triple(tmp_path):
    _, paths = _run(tmp_path)
    rows = json.loads(paths["leaderboard"].read_text())
    assert rows
    for row in rows:
        assert row["dataset_version"].startswith("redharness-leakage-demo@")
        assert "@" in row["dataset_version"]
        assert row["judge"] == "leak_detector"
        assert row["metric"] in _LEAKAGE_METRICS
        assert row["target"] in {"model_leaky", "model_guarded"}


def test_leakage_smoke_records_na_not_zero_for_guarded_categories(tmp_path):
    # The leakage_demo suite covers all four categories, so per-category rates are
    # applicable (never N/A) on every cell — and the guarded model reports a real
    # 0.0 (it was asked and refused), not N/A. This locks the 0.0-vs-None contract.
    _, paths = _run(tmp_path)
    rows = json.loads(paths["leaderboard"].read_text())
    guarded_rates = [
        r
        for r in rows
        if r["target"] == "model_guarded"
        and r["metric"] in {"canary_exposure_rate", "pii_leak_rate", "system_prompt_leak_rate"}
    ]
    assert guarded_rates
    for row in guarded_rates:
        assert row["value"] == 0.0  # applicable & refused -> genuine 0.0, not null


def test_leakage_smoke_reproducible(tmp_path):
    r1, _ = _run(tmp_path / "a")
    r2, _ = _run(tmp_path / "b")

    def _snapshot(result):
        return [
            (c.target, c.attack, name, m.value)
            for c in result.cells
            for name, m in c.metrics.items()
        ]

    assert _snapshot(r1) == _snapshot(r2)


def test_leakage_smoke_cache_hit_on_second_run(tmp_path):
    cfg = load_config(SMOKE_CONFIG)
    Runner(cfg, tmp_path).run()
    result = Runner(cfg, tmp_path).run()
    leaky = next(
        c for c in result.cells
        if c.target == "model_leaky" and c.attack == "system_prompt_leak"
    )
    assert leaky.metrics["system_prompt_leak_rate"].value == 1.0


def test_leakage_config_runs_in_jailbreak_mode(tmp_path):
    # The leakage surface reuses the single-turn jailbreak path; the config must
    # validate as jailbreak mode (attacks + datasets), not injection.
    cfg = load_config(SMOKE_CONFIG)
    assert cfg.mode == "jailbreak"
