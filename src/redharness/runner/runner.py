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
from redharness.core.judge import Judge
from redharness.core.metric import ScoredAttempts
from redharness.core.models import Attempt, Behavior
from redharness.core.target import Target
from redharness.errors import RedharnessError
from redharness.runner.agent_loop import run_agent_loop
from redharness.runner.build import (
    SPEC_ATTR,
    build_attack,
    build_dataset,
    build_injection,
    build_judge,
    build_metric,
    build_scenario_source,
    build_target,
)
from redharness.runner.cache import AttemptCache, params_hash
from redharness.runner.result import CellResult, RunResult


def _plugin_params(plugin: object) -> dict:
    """The params of the spec a plugin was built from (empty if none)."""
    spec = getattr(plugin, SPEC_ATTR, None)
    return dict(spec.params) if spec is not None else {}


def _plugin_params_hash(plugin: object) -> str:
    """Hash the params of the spec a plugin was built from (empty if none)."""
    return params_hash(_plugin_params(plugin))


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
        judges = [build_judge(s) for s in self.config.judges]
        metrics = [build_metric(name) for name in self.config.metrics]

        with self.transcript_path.open("w") as transcripts:
            if self.config.mode == "injection":
                cells = self._run_injection(judges, metrics, transcripts)
            else:
                cells = self._run_jailbreak(judges, metrics, transcripts)

        return RunResult(
            run_id=self.run_id,
            run_name=self.config.run_name,
            seed=self.config.seed,
            cells=cells,
            transcript_path=str(self.transcript_path),
        )

    def _run_jailbreak(self, judges, metrics, transcripts) -> list[CellResult]:
        targets = [build_target(s) for s in self.config.targets]
        attacks = [build_attack(s) for s in self.config.attacks]
        datasets = [build_dataset(s) for s in self.config.datasets]
        loaded = {ds.name: (ds.version, ds.load()) for ds in datasets}

        cells: list[CellResult] = []
        for dataset in datasets:
            version, behaviors = loaded[dataset.name]
            for target in targets:
                for attack in attacks:
                    attempts = self._run_attack(attack, target, behaviors, transcripts)
                    for judge in judges:
                        cells.append(
                            self._score_cell(
                                attack.name, target.name, dataset.name, version,
                                judge, behaviors, attempts, metrics,
                            )
                        )
        return cells

    def _run_injection(self, judges, metrics, transcripts) -> list[CellResult]:
        """Run the agentic injection matrix: injection x target x suite x judge."""
        targets = [build_target(s) for s in self.config.targets]
        injections = [build_injection(s) for s in self.config.injections]
        sources = [build_scenario_source(s) for s in self.config.scenarios]
        loaded = {src.suite: (src.version, src.load()) for src in sources}

        cells: list[CellResult] = []
        for source in sources:
            version, scenarios = loaded[source.suite]
            behaviors = [_scenario_behavior(s) for s in scenarios]
            for target in targets:
                for injection in injections:
                    attempts = self._run_injection_attack(
                        injection, target, scenarios, transcripts
                    )
                    for judge in judges:
                        cells.append(
                            self._score_cell(
                                injection.name, target.name, source.suite, version,
                                judge, behaviors, attempts, metrics,
                            )
                        )
        return cells

    def _run_injection_attack(
        self, injection, target, scenarios, transcripts
    ) -> list[Attempt]:
        """Drive ``target`` through each scenario under ``injection``, with caching."""
        target_hash = _plugin_params_hash(target)
        # max_steps is passed into run_agent_loop and changes the attempt (a plan
        # longer than max_steps completes differently), so it must be part of the
        # cache key — same params-in-key invariant the jailbreak path upholds.
        # Folding it into the injection-side hash keeps AttemptCache's signature
        # unchanged while making the key sensitive to max_steps.
        injection_hash = params_hash(
            {
                "params": _plugin_params(injection),
                "max_steps": self.config.max_steps,
            }
        )
        all_attempts: list[Attempt] = []
        for scenario in scenarios:
            cached = self.cache.get(
                target.name, target_hash, injection.name, injection_hash,
                scenario.name, scenario.user_task,
            )
            if cached is None:
                payload = injection.build_injection(scenario)
                attempt = run_agent_loop(
                    scenario, target, payload, injection.name, self.config.max_steps
                )
                cached = [attempt]
                self.cache.put(
                    target.name, target_hash, injection.name, injection_hash,
                    scenario.name, scenario.user_task, cached,
                )
            for attempt in cached:
                transcripts.write(json.dumps(attempt.model_dump()) + "\n")
            all_attempts.extend(cached)
        return all_attempts

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
        attack_name: str,
        target_name: str,
        dataset_name: str,
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
                    f"attack {attack_name!r} produced an attempt for unknown "
                    f"behavior_id {a.behavior_id!r}; dataset {dataset_name!r} has: {known}"
                )
            scored.append((behavior, a, judge.score(behavior, a)))
        cell = CellResult(
            attack=attack_name,
            target=target_name,
            dataset=dataset_name,
            dataset_version=version,
            judge=judge.name,
        )
        for metric in metrics:
            cell.metrics[metric.name] = metric.compute(scored)
        return cell


def _scenario_behavior(scenario) -> Behavior:
    """Synthesise the Behavior wrapper a scenario presents to the scoring path.

    One scenario maps to one behavior (id = scenario id, prompt = benign user
    task), so the existing per-behavior scoring, report and leaderboard machinery
    works unchanged for the injection surface.
    """
    return Behavior(
        id=scenario.name,
        prompt=scenario.user_task,
        category=scenario.suite,
        expected="should_refuse",
    )
