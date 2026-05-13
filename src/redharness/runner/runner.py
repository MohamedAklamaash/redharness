"""The matrix executor.

Given a validated :class:`RunConfig`, the runner instantiates plugins, iterates
the attack x target x dataset x judge matrix deterministically, persists every
transcript to JSONL, caches attempts per (target, attack, behavior), computes the
configured metrics per cell, and returns a structured :class:`RunResult`.

Determinism: iteration order follows config order, the cache key is content-based,
and the offline targets/judges carry no randomness — so two runs of the smoke
config produce byte-identical results.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from redharness.config import RunConfig
from redharness.core.attack import Attack
from redharness.core.dataset import Dataset
from redharness.core.judge import Judge
from redharness.core.metric import ScoredAttempts
from redharness.core.models import Attempt, Behavior
from redharness.core.target import Target
from redharness.errors import RedharnessError
from redharness.runner.build import (
    SPEC_ATTR,
    build_attack,
    build_dataset,
    build_judge,
    build_metric,
    build_target,
)
from redharness.runner.cache import AttemptCache, params_hash
from redharness.runner.result import CellResult, RunResult


def _plugin_params_hash(plugin: object) -> str:
    """Hash the params of the spec a plugin was built from (empty if none)."""
    spec = getattr(plugin, SPEC_ATTR, None)
    return params_hash(dict(spec.params)) if spec is not None else params_hash({})


class Runner:
    """Executes a run config and writes its artifacts under ``runs/<run_id>/``."""

    def __init__(self, config: RunConfig, runs_dir: Path) -> None:
        self.config = config
        self.run_id = config.run_name
        runs_root = Path(runs_dir).resolve()
        self.run_dir = (runs_root / self.run_id).resolve()
        # Defence in depth: run_name is validated to a safe slug at config load,
        # but assert the resolved dir stays within runs_dir so a future bypass
        # of that validator can never escape the runs root and overwrite files.
        if self.run_dir != runs_root and runs_root not in self.run_dir.parents:
            raise RedharnessError(
                f"run_name {self.run_id!r} escapes the runs directory {runs_root}"
            )
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_path = self.run_dir / "transcripts.jsonl"
        self.cache = AttemptCache(self.run_dir / "cache")

    def run(self) -> RunResult:
        random.seed(self.config.seed)
        targets = [build_target(s) for s in self.config.targets]
        attacks = [build_attack(s) for s in self.config.attacks]
        datasets = [build_dataset(s) for s in self.config.datasets]
        judges = [build_judge(s) for s in self.config.judges]
        metrics = [build_metric(name) for name in self.config.metrics]

        loaded = {ds.name: (ds.version, ds.load()) for ds in datasets}

        cells: list[CellResult] = []
        with self.transcript_path.open("w") as transcripts:
            for dataset in datasets:
                version, behaviors = loaded[dataset.name]
                for target in targets:
                    for attack in attacks:
                        attempts = self._run_attack(
                            attack, target, behaviors, transcripts
                        )
                        for judge in judges:
                            cells.append(
                                self._score_cell(
                                    attack,
                                    target,
                                    dataset,
                                    version,
                                    judge,
                                    behaviors,
                                    attempts,
                                    metrics,
                                )
                            )

        return RunResult(
            run_id=self.run_id,
            run_name=self.config.run_name,
            seed=self.config.seed,
            cells=cells,
            transcript_path=str(self.transcript_path),
        )

    def _run_attack(
        self,
        attack: Attack,
        target: Target,
        behaviors: list[Behavior],
        transcripts,
    ) -> list[Attempt]:
        """Run one attack against one target over all behaviors, with caching."""
        target_hash = _plugin_params_hash(target)
        attack_hash = _plugin_params_hash(attack)
        all_attempts: list[Attempt] = []
        for behavior in behaviors:
            cached = self.cache.get(
                target.name, target_hash, attack.name, attack_hash,
                behavior.id, behavior.prompt,
            )
            if cached is None:
                cached = attack.run(behavior, target)
                self.cache.put(
                    target.name, target_hash, attack.name, attack_hash,
                    behavior.id, behavior.prompt, cached,
                )
            for attempt in cached:
                transcripts.write(json.dumps(attempt.model_dump()) + "\n")
            all_attempts.extend(cached)
        return all_attempts

    def _score_cell(
        self,
        attack: Attack,
        target: Target,
        dataset: Dataset,
        version: str,
        judge: Judge,
        behaviors: list[Behavior],
        attempts: list[Attempt],
        metrics,
    ) -> CellResult:
        by_id = {b.id: b for b in behaviors}
        scored: ScoredAttempts = []
        for a in attempts:
            behavior = by_id.get(a.behavior_id)
            if behavior is None:
                known = ", ".join(sorted(by_id)) or "(none)"
                raise RedharnessError(
                    f"attack {attack.name!r} produced an attempt for unknown "
                    f"behavior_id {a.behavior_id!r}; dataset {dataset.name!r} has: {known}"
                )
            scored.append((behavior, a, judge.score(behavior, a)))
        cell = CellResult(
            attack=attack.name,
            target=target.name,
            dataset=dataset.name,
            dataset_version=version,
            judge=judge.name,
        )
        for metric in metrics:
            cell.metrics[metric.name] = metric.compute(scored)
        return cell
