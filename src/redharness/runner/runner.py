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
from redharness.core.models import Attempt, Behavior, Message
from redharness.core.target import Target
from redharness.errors import RedharnessError, RunBudgetExceeded
from redharness.runner.agent_loop import run_agent_loop
from redharness.runner.budget import BudgetedTarget, QueryBudget
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
        # One coherent run budget, charged the retry-inclusive real-call count at
        # the innermost call site (see runner.budget). Cell judges' graders are real
        # provider calls too, so wrap them so scoring-phase calls also count.
        self.budget = QueryBudget(self.config.max_queries, self.run_id)
        judges = [build_judge(s) for s in self.config.judges]
        for judge in judges:
            _wrap_grader(judge, self.budget)
        metrics = [build_metric(name) for name in self.config.metrics]
        self._print_estimate()

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
        for attack in attacks:
            _wrap_attack_providers(attack, self.budget)
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
        # Cache keys use the RAW target; the agent loop drives a budget-wrapped one
        # so every real model call is charged (cache hits never reach generate).
        budgeted = BudgetedTarget(target, self.budget)
        all_attempts: list[Attempt] = []
        for scenario in scenarios:
            cached = self.cache.get(
                target.name, target_hash, injection.name, injection_hash,
                scenario.name, scenario.user_task,
            )
            if cached is None:
                payload = injection.build_injection(scenario)
                attempt = run_agent_loop(
                    scenario, budgeted, payload, injection.name, self.config.max_steps
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
        """Run one attack against one target over all behaviors, with caching.

        Per-behavior execution is error-tolerant: an attack that raises records a
        typed *errored* attempt and the run continues over the rest of the matrix.
        An errored attempt is never written to the cache, so it can never be
        served later as a (false) success.
        """
        target_hash = _plugin_params_hash(target)
        # Fold the run-level query budget into the attack cache key (mirrors the
        # max_steps fix); the attacker sub-spec and max_iters already live in the
        # attack's own params hash, so changing them also busts the key.
        attack_hash = params_hash(
            {"params": _plugin_params(attack), "max_queries": self.config.max_queries}
        )
        # Cache keys use the RAW target; the attack drives a budget-wrapped one so
        # every real provider call is charged at the call site (cache hits never
        # reach generate, so they are never charged).
        budgeted = BudgetedTarget(target, self.budget)
        all_attempts: list[Attempt] = []
        for behavior in behaviors:
            cached = self.cache.get(
                target.name, target_hash, attack.name, attack_hash,
                behavior.id, behavior.prompt,
            )
            if cached is None:
                try:
                    cached = attack.run(behavior, budgeted)
                except RunBudgetExceeded:
                    # Fail-closed: a budget abort must propagate, never be swallowed
                    # into an errored attempt that lets the run continue overspending.
                    raise
                except RedharnessError as exc:
                    # Expected typed failure (e.g. a transient TargetRuntimeError):
                    # record an errored attempt and continue the rest of the matrix.
                    cached = [_errored_attempt(behavior, attack.name, target.name, exc)]
                except Exception as exc:  # defensive catch-all, sanitized + truncated
                    cached = [_errored_attempt(behavior, attack.name, target.name, exc)]
                else:
                    self.cache.put(
                        target.name, target_hash, attack.name, attack_hash,
                        behavior.id, behavior.prompt, cached,
                    )
            for attempt in cached:
                transcripts.write(json.dumps(attempt.model_dump()) + "\n")
            all_attempts.extend(cached)
        return all_attempts

    def _print_estimate(self) -> None:
        """Print a coarse pre-run cost estimate before any provider is queried."""
        cfg = self.config
        if cfg.mode == "injection":
            axes = len(cfg.targets) * len(cfg.injections) * len(cfg.scenarios)
            shape = (
                f"{len(cfg.targets)} target(s) x {len(cfg.injections)} injection(s) "
                f"x {len(cfg.scenarios)} suite(s)"
            )
        else:
            axes = len(cfg.targets) * len(cfg.attacks) * len(cfg.datasets)
            shape = (
                f"{len(cfg.targets)} target(s) x {len(cfg.attacks)} attack(s) "
                f"x {len(cfg.datasets)} dataset(s)"
            )
        budget = "unbounded" if cfg.max_queries is None else str(cfg.max_queries)
        print(
            f"[redharness] run {self.run_id!r}: {axes} cell group(s) ({shape}); "
            f"query budget: {budget}",
            flush=True,
        )

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


#: Cap on the persisted error string. The typed adapter errors already avoid
#: embedding secrets, but truncate defensively so an unexpected catch-all can never
#: spill a large/sensitive payload into a transcript.
_MAX_ERROR_LEN = 200


def _safe_error(exc: Exception) -> str:
    """A sanitized, length-capped ``Type: message`` string safe to persist."""
    detail = str(exc)
    if len(detail) > _MAX_ERROR_LEN:
        detail = detail[:_MAX_ERROR_LEN] + "...(truncated)"
    return f"{type(exc).__name__}: {detail}"


def _errored_attempt(
    behavior: Behavior, attack_name: str, target_name: str, exc: Exception
) -> Attempt:
    """A typed, non-success attempt standing in for an attack that raised."""
    return Attempt(
        behavior_id=behavior.id,
        attack_name=attack_name,
        target_name=target_name,
        transcript=[
            Message(role="user", content=behavior.prompt),
            Message(role="assistant", content=""),
        ],
        query_count=0,
        metadata={"errored": True, "error": _safe_error(exc)},
    )


def _wrap_grader(judge: Judge, budget: QueryBudget) -> None:
    """Wrap a judge's grader Target so its real provider calls charge the budget."""
    grader = getattr(judge, "grader", None)
    if isinstance(grader, Target) and not isinstance(grader, BudgetedTarget):
        judge.grader = BudgetedTarget(grader, budget)


def _wrap_attack_providers(attack: Attack, budget: QueryBudget) -> None:
    """Wrap an attack's injected attacker + in-loop judge grader (e.g. PAIR).

    These providers live inside the attack (built by the build layer), so the
    runner wraps them here, once, after construction — so PAIR charges every
    outbound call (attacker + target + judge) at the innermost call site.
    """
    attacker = getattr(attack, "attacker", None)
    if isinstance(attacker, Target) and not isinstance(attacker, BudgetedTarget):
        attack.attacker = BudgetedTarget(attacker, budget)
    judge = getattr(attack, "judge", None)
    if isinstance(judge, Judge):
        _wrap_grader(judge, budget)


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
