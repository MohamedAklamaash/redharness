"""The ``redharness`` command-line interface.

Three subcommands:
  * ``run <config>``      — execute the eval and write a report + leaderboard.
  * ``validate <config>`` — parse and validate a config without running.
  * ``list``              — show every registered plugin by axis.

Errors are mapped to clear messages and a non-zero exit so CI fails loudly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

import redharness.plugins  # noqa: F401  (populates registries)
from redharness.config import load_config
from redharness.core.registry import registry
from redharness.errors import RedharnessError
from redharness.report import write_reports
from redharness.runner import Runner

app = typer.Typer(
    add_completion=False,
    help="An open-source LLM red-teaming and safety benchmark harness.",
    no_args_is_help=True,
)


@app.command()
def run(
    config: Path = typer.Argument(..., help="Path to a YAML run config."),
    runs_dir: Path = typer.Option(Path("runs"), help="Where to write run artifacts."),
) -> None:
    """Execute a run config and write a report + leaderboard.json."""
    cfg = load_config(config)
    runner = Runner(cfg, runs_dir)
    result = runner.run()
    paths = write_reports(result, runner.run_dir)

    typer.echo(f"run '{result.run_id}' complete: {len(result.cells)} cells")
    typer.echo(f"  transcripts: {result.transcript_path}")
    typer.echo(f"  report (md): {paths['markdown']}")
    typer.echo(f"  report (html): {paths['html']}")
    typer.echo(f"  leaderboard: {paths['leaderboard']}")


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
