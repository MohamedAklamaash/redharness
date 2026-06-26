"""The ``redharness`` command-line interface.

Subcommands:
  * ``run <config>``           — execute the eval and write a report + leaderboard.
  * ``validate <config>``      — parse and validate a config without running.
  * ``list``                   — show every registered plugin by axis.
  * ``judge-agreement <run>``  — re-score a run's transcripts under multiple judges.
  * ``dashboard``              — launch the Streamlit leaderboard web app.

Errors are mapped to clear messages and a non-zero exit so CI fails loudly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

import redharness.plugins  # noqa: F401  (populates registries)
from redharness.analysis import judge_spec, run_judge_agreement
from redharness.config import load_config
from redharness.core.registry import registry
from redharness.errors import DashboardError, RedharnessError
from redharness.report import write_reports
from redharness.runner import Runner
from redharness.runner.trials import run_trials

app = typer.Typer(
    add_completion=False,
    help="An open-source LLM red-teaming and safety benchmark harness.",
    no_args_is_help=True,
)


@app.command()
def run(
    config: Path = typer.Argument(..., help="Path to a YAML run config."),
    runs_dir: Path = typer.Option(Path("runs"), help="Where to write run artifacts."),
    concurrency: int = typer.Option(
        None, min=1, max=64, help="Override config concurrency (bounded worker threads)."
    ),
    trials: int = typer.Option(
        None, min=1, max=100, help="Repeat the matrix under N seeds and report mean + CI."
    ),
) -> None:
    """Execute a run config and write a report + leaderboard.json."""
    cfg = load_config(config)
    overrides: dict = {}
    if concurrency is not None:
        overrides["concurrency"] = concurrency
    if trials is not None:
        overrides["trials"] = trials
    if overrides:
        cfg = cfg.model_copy(update=overrides)

    if cfg.trials > 1:
        result, run_dir = run_trials(cfg, runs_dir)
    else:
        runner = Runner(cfg, runs_dir)
        result, run_dir = runner.run(), runner.run_dir
    paths = write_reports(result, run_dir)

    typer.echo(f"run '{result.run_id}' complete: {len(result.cells)} cells")
    typer.echo(f"  transcripts: {result.transcript_path}")
    typer.echo(f"  report (md): {paths['markdown']}")
    typer.echo(f"  report (html): {paths['html']}")
    typer.echo(f"  leaderboard: {paths['leaderboard']}")


@app.command(name="judge-agreement")
def judge_agreement(
    run_dir: Path = typer.Argument(..., help="A finished run directory (with transcripts.jsonl)."),
    judge: list[str] = typer.Option(
        ..., "--judge", help="Judge name to re-score under (repeatable; >=2 required)."
    ),
    grader: str = typer.Option(
        "reference", help="Grader target for grader-backed judges (rubric/strongreject)."
    ),
) -> None:
    """Re-score a run's transcripts under multiple judges and report Cohen's kappa."""
    specs = [judge_spec(name, grader) for name in judge]
    report = run_judge_agreement(run_dir, specs)
    typer.echo(f"judge-agreement over {report.n_attempts} attempt(s) in {report.run_dir}")
    typer.echo("per-judge ASR:")
    for name, value in report.asr.items():
        typer.echo(f"  {name}: {value:.4f}")
    typer.echo("pairwise agreement:")
    for pair in report.pairwise:
        typer.echo(
            f"  {pair.judge_a} vs {pair.judge_b}: "
            f"raw={pair.raw_agreement:.4f} kappa={pair.cohen_kappa:.4f}"
        )
    typer.echo(f"  written: {Path(report.run_dir) / 'judge_agreement.json'}")


@app.command()
def validate(
    config: Path = typer.Argument(..., help="Path to a YAML run config."),
) -> None:
    """Validate a run config without executing it."""
    cfg = load_config(config)
    if cfg.mode == "injection":
        axes = (
            f"{len(cfg.injections)} injection(s), {len(cfg.scenarios)} scenario suite(s)"
        )
    else:
        axes = f"{len(cfg.attacks)} attack(s), {len(cfg.datasets)} dataset(s)"
    typer.echo(
        f"config OK ({cfg.mode} mode): {len(cfg.targets)} target(s), {axes}, "
        f"{len(cfg.judges)} judge(s), {len(cfg.metrics)} metric(s)"
    )


@app.command()
def dashboard(
    runs_dir: Path = typer.Option(Path("runs"), help="Directory of run artifacts to aggregate."),
    port: int = typer.Option(8501, help="Port for the Streamlit server."),
) -> None:
    """Launch the Streamlit leaderboard web app over a runs directory.

    Aggregates every runs-dir/*/leaderboard.json and serves a filterable, per-surface
    dashboard. Requires the optional 'dashboard' extra (see the README / docs OVERVIEW).
    """
    if runs_dir.exists() and not runs_dir.is_dir():
        raise DashboardError(f"runs path is not a directory: {runs_dir}")

    from redharness.dashboard.launch import launch_dashboard

    typer.echo(f"launching dashboard at http://localhost:{port} (runs dir: {runs_dir})")
    code = launch_dashboard(runs_dir, port)
    if code != 0:
        raise typer.Exit(code)


@app.command(name="list")
def list_plugins() -> None:
    """List every registered plugin grouped by axis."""
    for axis, reg in registry.by_axis().items():
        names = reg.names()
        typer.echo(f"{axis}:")
        for name in names:
            typer.echo(f"  - {name}")
        if not names:
            typer.echo("  (none)")


def main() -> None:
    """Console-script entry point with typed-error handling."""
    try:
        app()
    except RedharnessError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
