"""Multi-seed trials: repeat the matrix under N seeds and aggregate to mean + CI.

A single run reports one number per cell. For a *stochastic* live target that number
varies seed to seed, so a single sample understates the uncertainty. ``trials`` runs
the whole matrix under seeds ``seed .. seed+trials-1`` and aggregates each metric to
its mean across trials plus a bootstrap confidence interval (seeded from the run seed
for determinism). For deterministic reference targets every trial is identical, so the
mean equals the single-run value and the interval has width zero — which is exactly
what the offline tests lock. The default (no trials) path never reaches this module.
"""

from __future__ import annotations

from pathlib import Path

from redharness.config import RunConfig
from redharness.core.metric import MetricResult
from redharness.metrics.agreement import bootstrap_ci
from redharness.runner.result import CellResult, RunResult
from redharness.runner.runner import Runner


def _cell_key(cell: CellResult) -> tuple[str, str, str, str]:
    return (cell.attack, cell.target, cell.dataset, cell.judge)


def _aggregate_metric(name: str, values: list[float | None], seed: int) -> MetricResult:
    """Mean + bootstrap CI of one metric's value across trials (ignoring N/A)."""
    present = [v for v in values if v is not None]
    if not present:
        return MetricResult(name=name, value=None, breakdown={"trial_values": values})
    mean = sum(present) / len(present)
    lo, hi = bootstrap_ci(present, seed=seed)
    return MetricResult(
        name=name,
        value=round(mean, 6),
        breakdown={"n_trials": len(values), "trial_values": values},
        ci_low=None if lo is None else round(lo, 6),
        ci_high=None if hi is None else round(hi, 6),
    )


def aggregate_trials(config: RunConfig, results: list[RunResult]) -> RunResult:
    """Combine per-trial :class:`RunResult`s into one mean+CI :class:`RunResult`."""
    template = results[0]
    by_key: dict[tuple, list[CellResult]] = {}
    for result in results:
        for cell in result.cells:
            by_key.setdefault(_cell_key(cell), []).append(cell)

    cells: list[CellResult] = []
    for cell in template.cells:
        trial_cells = by_key[_cell_key(cell)]
        aggregated = CellResult(
            attack=cell.attack,
            target=cell.target,
            dataset=cell.dataset,
            dataset_version=cell.dataset_version,
            judge=cell.judge,
        )
        for metric_name in cell.metrics:
            values = [tc.metrics[metric_name].value for tc in trial_cells]
            aggregated.metrics[metric_name] = _aggregate_metric(
                metric_name, values, config.seed
            )
        cells.append(aggregated)

    return RunResult(
        run_id=config.run_name,
        run_name=config.run_name,
        seed=config.seed,
        cells=cells,
        transcript_path=template.transcript_path,
    )


def run_trials(config: RunConfig, runs_dir: Path) -> tuple[RunResult, Path]:
    """Run the matrix once per seed and return the aggregated result + its run dir.

    Each trial executes into ``runs_dir/<run_name>/trials/<run_name>-trial-<seed>/``
    so the per-trial artifacts are kept, and the aggregated report/leaderboard are
    written by the caller into ``runs_dir/<run_name>/``.
    """
    base = (Path(runs_dir).resolve() / config.run_name).resolve()
    trials_dir = base / "trials"
    results: list[RunResult] = []
    for index in range(config.trials):
        seed = config.seed + index
        trial_cfg = config.model_copy(
            update={
                "seed": seed,
                "run_name": f"{config.run_name}-trial-{seed}",
                "trials": 1,
            }
        )
        results.append(Runner(trial_cfg, trials_dir).run())
    return aggregate_trials(config, results), base
