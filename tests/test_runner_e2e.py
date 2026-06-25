"""End-to-end smoke test: run configs/smoke.yaml offline in a tmp dir."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from redharness.config import RunConfig, load_config
from redharness.report import write_reports
from redharness.report.render import build_leaderboard
from redharness.runner import Runner

SMOKE_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "smoke.yaml"


def _run(tmp_path) -> tuple:
    cfg = load_config(SMOKE_CONFIG)
    runner = Runner(cfg, tmp_path)
    result = runner.run()
    paths = write_reports(result, runner.run_dir)
    return result, paths


def test_smoke_produces_all_artifacts(tmp_path):
    result, paths = _run(tmp_path)
    assert Path(result.transcript_path).exists()
    assert paths["markdown"].exists()
    assert paths["html"].exists()
    assert paths["leaderboard"].exists()
    # 2 attacks x 2 targets x 1 dataset x 2 judges = 8 cells.
    assert len(result.cells) == 8


def test_smoke_leaderboard_has_provenance_triple(tmp_path):
    _, paths = _run(tmp_path)
    rows = json.loads(paths["leaderboard"].read_text())
    assert rows
    for row in rows:
        assert row["dataset_version"].startswith("redharness-demo@")
        assert row["judge"] in {"refusal_match", "rubric"}
        assert row["metric"] in {"asr", "asr_at_k", "refusal_rate", "strongreject_score", "frr"}
        assert row["target"] in {"aligned-reference", "permissive-reference"}


def test_smoke_deterministic_metric_values(tmp_path):
    result, _ = _run(tmp_path)
    by_cell = {(c.target, c.attack, c.judge): c for c in result.cells}

    # Strict reference: static replay refuses every harmful behavior (ASR 0) and
    # over-refuses the XSTest-style benign prompts (FRR 4/20 = 0.2).
    strict_static = by_cell[("aligned-reference", "static", "refusal_match")]
    assert strict_static.metrics["asr"].value == 0.0
    assert strict_static.metrics["refusal_rate"].value == 1.0
    assert strict_static.metrics["frr"].value == 0.2
    assert strict_static.metrics["strongreject_score"].value == 0.0

    # Template attack has a bypass template -> all harmful behaviors jailbroken,
    # and the same bypass flips the over-refused benign prompts back to compliance.
    strict_template = by_cell[("aligned-reference", "template", "refusal_match")]
    assert strict_template.metrics["asr"].value == 1.0
    assert strict_template.metrics["asr_at_k"].value == 1.0
    assert strict_template.metrics["frr"].value == 0.0

    # Lenient reference: narrow topics, so direct replay already complies with most
    # harmful probes (ASR 24/30 = 0.8) and never over-refuses benign prompts.
    lenient_static = by_cell[("permissive-reference", "static", "refusal_match")]
    assert lenient_static.metrics["asr"].value == 0.8
    assert lenient_static.metrics["refusal_rate"].value == pytest.approx(0.2)
    assert lenient_static.metrics["frr"].value == 0.0
    assert lenient_static.metrics["strongreject_score"].value == 0.8

    lenient_template = by_cell[("permissive-reference", "template", "refusal_match")]
    assert lenient_template.metrics["asr"].value == 1.0

    # The strict reference is strictly safer than the lenient one under direct replay.
    assert strict_static.metrics["asr"].value < lenient_static.metrics["asr"].value


def test_runner_is_reproducible(tmp_path):
    r1, _ = _run(tmp_path / "a")
    r2, _ = _run(tmp_path / "b")
    v1 = [(c.target, c.attack, c.judge, c.metrics["asr"].value) for c in r1.cells]
    v2 = [(c.target, c.attack, c.judge, c.metrics["asr"].value) for c in r2.cells]
    assert v1 == v2


def test_runner_cache_hit_on_second_run(tmp_path):
    cfg = load_config(SMOKE_CONFIG)
    Runner(cfg, tmp_path).run()
    # Second run reuses the on-disk attempt cache; results must be identical.
    result = Runner(cfg, tmp_path).run()
    rows = build_leaderboard(result)
    assert any(
        r["attack"] == "template" and r["metric"] == "asr" and r["value"] == 1.0
        for r in rows
    )


def _config(run_name: str, bypass: list[str] | None, target_name: str = "reference"):
    params: dict = {}
    if bypass is not None:
        params["bypass_markers"] = bypass
    return RunConfig.model_validate(
        {
            "run_name": run_name,
            "targets": [{"name": "reference", "params": {"name": target_name, **params}}],
            "attacks": [{"name": "template"}],
            "datasets": [{"name": "demo"}],
            "judges": [{"name": "refusal_match"}],
            "metrics": ["asr"],
        }
    )


def _template_asr(result, target_name: str = "reference") -> float:
    cell = next(
        c for c in result.cells if c.attack == "template" and c.target == target_name
    )
    return cell.metrics["asr"].value


# --- Finding 1: cache key folds in plugin params (no stale cross-param hits) ---


def test_cache_invalidated_on_attack_or_target_param_change(tmp_path):
    # First run: bypass marker present -> template jailbreak succeeds (ASR 1.0).
    first = Runner(_config("rerun", bypass=["ignore the previous framing"]), tmp_path).run()
    assert _template_asr(first) == 1.0

    # Same run_name, params changed (no bypass) -> must NOT serve the stale 1.0;
    # the strict default now refuses every template, so ASR drops to 0.0.
    second = Runner(_config("rerun", bypass=[]), tmp_path).run()
    assert _template_asr(second) == 0.0

    # Re-running the original params again still reuses the correct cached 1.0.
    third = Runner(_config("rerun", bypass=["ignore the previous framing"]), tmp_path).run()
    assert _template_asr(third) == 1.0


def test_two_same_named_targets_differing_only_in_params(tmp_path):
    # Two "reference" targets in one run that differ only in bypass_markers must each
    # get their own correct ASR — not collide on a shared (name) cache key.
    cfg = RunConfig.model_validate(
        {
            "run_name": "twins",
            "targets": [
                {"name": "reference", "params": {"name": "reference", "bypass_markers": []}},
                {
                    "name": "reference",
                    "params": {
                        "name": "reference",
                        "bypass_markers": ["ignore the previous framing"],
                    },
                },
            ],
            "attacks": [{"name": "template"}],
            "datasets": [{"name": "demo"}],
            "judges": [{"name": "refusal_match"}],
            "metrics": ["asr"],
        }
    )
    result = Runner(cfg, tmp_path).run()
    # Both targets share the name "reference"; distinguish their cells by ASR value.
    asrs = sorted(
        c.metrics["asr"].value for c in result.cells if c.attack == "template"
    )
    assert asrs == [0.0, 1.0]


# --- Finding 2: run_dir cannot escape runs_dir (defence in depth) -------------


def test_runner_rejects_run_name_escaping_runs_dir(tmp_path):
    from redharness.errors import RedharnessError

    cfg = _config("ok", bypass=[])
    cfg.run_name = "../escape"  # bypass the config validator to test the runner guard
    with pytest.raises(RedharnessError, match="escapes"):
        Runner(cfg, tmp_path / "runs")


# --- Finding 5: build_* is self-sufficient without importing redharness.plugins -


def test_build_resolves_without_preimporting_plugins():
    # Run in a fresh interpreter that does NOT import redharness.plugins, proving
    # build.py populates the registries on its own. (conftest imports plugins in
    # this process, so a subprocess is the only honest check.)
    import subprocess
    import sys

    script = (
        "from redharness.config import PluginSpec\n"
        "from redharness.runner.build import build_target, build_attack\n"
        "t = build_target(PluginSpec(name='reference'))\n"
        "a = build_attack(PluginSpec(name='static'))\n"
        "assert t.name == 'reference' and a.name == 'static'\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


# --- Finding 4: unknown behavior_id from an attack raises a typed error -------


def test_unknown_behavior_id_raises_typed_error(tmp_path):
    from redharness.core.attack import Attack
    from redharness.core.models import Attempt, Message
    from redharness.core.registry import registry
    from redharness.errors import RedharnessError

    class _RogueAttack(Attack):
        name = "_rogue_id"

        def run(self, behavior, target):
            target.generate([Message(role="user", content=behavior.prompt)])
            return [
                Attempt(
                    behavior_id="synthesized-does-not-exist",
                    attack_name=self.name,
                    target_name=target.name,
                    transcript=[Message(role="user", content="x")],
                )
            ]

    registry.attacks.register("_rogue_id")(_RogueAttack)
    cfg = RunConfig.model_validate(
        {
            "run_name": "rogue",
            "targets": [{"name": "reference"}],
            "attacks": [{"name": "_rogue_id"}],
            "datasets": [{"name": "demo"}],
            "judges": [{"name": "refusal_match"}],
            "metrics": ["asr"],
        }
    )
    with pytest.raises(RedharnessError, match="unknown behavior_id"):
        Runner(cfg, tmp_path).run()


def test_empty_dataset_yields_zero_metrics(tmp_path):
    cfg = RunConfig.model_validate(
        {
            "run_name": "empty",
            "targets": [{"name": "reference"}],
            "attacks": [{"name": "static"}],
            "datasets": [{"name": "_empty_test"}],
            "judges": [{"name": "refusal_match"}],
            "metrics": ["asr", "frr"],
        }
    )
    from redharness.core.dataset import Dataset
    from redharness.core.registry import registry

    class _EmptyDataset(Dataset):
        name = "_empty_test"

        @property
        def version(self) -> str:
            return "_empty@0"

        def load(self):
            return []

    registry.datasets.register("_empty_test")(_EmptyDataset)
    result = Runner(cfg, tmp_path).run()
    for cell in result.cells:
        assert cell.metrics["asr"].value == 0.0
        assert cell.metrics["frr"].value == 0.0
