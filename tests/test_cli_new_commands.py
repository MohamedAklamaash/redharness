"""CLI coverage for the new flags/commands: judge-agreement, --trials, --concurrency."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from redharness.cli import app

runner = CliRunner()
SMOKE_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "smoke.yaml"


def test_run_with_concurrency_and_trials_flags(tmp_path):
    result = runner.invoke(
        app,
        ["run", str(SMOKE_CONFIG), "--runs-dir", str(tmp_path),
         "--concurrency", "4", "--trials", "2"],
    )
    assert result.exit_code == 0, result.stdout
    assert "complete" in result.stdout
    assert (tmp_path / "smoke" / "leaderboard.json").exists()
    assert (tmp_path / "smoke" / "trials").is_dir()


def test_judge_agreement_command(tmp_path):
    run = runner.invoke(app, ["run", str(SMOKE_CONFIG), "--runs-dir", str(tmp_path)])
    assert run.exit_code == 0, run.stdout

    result = runner.invoke(
        app,
        ["judge-agreement", str(tmp_path / "smoke"),
         "--judge", "refusal_match", "--judge", "rubric"],
    )
    assert result.exit_code == 0, result.stdout
    assert "per-judge ASR" in result.stdout
    assert "kappa" in result.stdout
    assert (tmp_path / "smoke" / "judge_agreement.json").exists()


def test_judge_agreement_one_judge_errors(tmp_path):
    runner.invoke(app, ["run", str(SMOKE_CONFIG), "--runs-dir", str(tmp_path)])
    result = runner.invoke(
        app, ["judge-agreement", str(tmp_path / "smoke"), "--judge", "refusal_match"]
    )
    assert result.exit_code == 1
