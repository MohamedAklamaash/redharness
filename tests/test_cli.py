"""Tests for the CLI commands and their error handling."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from redharness.cli import app, main

runner = CliRunner()
_CONFIGS = Path(__file__).resolve().parents[1] / "configs"
SMOKE_CONFIG = _CONFIGS / "smoke.yaml"
INJECTION_CONFIG = _CONFIGS / "injection_smoke.yaml"


def test_list_shows_every_axis():
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    for axis in ("targets", "attacks", "datasets", "judges", "metrics", "injections", "scenarios"):
        assert axis in result.stdout
    assert "reference" in result.stdout
    assert "indirect_injection" in result.stdout


def test_validate_injection_config_reports_mode():
    result = runner.invoke(app, ["validate", str(INJECTION_CONFIG)])
    assert result.exit_code == 0
    assert "injection mode" in result.stdout
    assert "injection(s)" in result.stdout


def test_list_shows_remote_dataset():
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "remote" in result.stdout


def test_validate_ok():
    result = runner.invoke(app, ["validate", str(SMOKE_CONFIG)])
    assert result.exit_code == 0
    assert "config OK" in result.stdout


def test_validate_unknown_plugin_does_not_crash_validation(tmp_path):
    # validate only checks schema, not plugin existence; an unknown name still parses.
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "targets: [nope]\nattacks: [static]\ndatasets: [demo]\n"
        "judges: [refusal_match]\nmetrics: [asr]"
    )
    result = runner.invoke(app, ["validate", str(cfg)])
    assert result.exit_code == 0


def test_run_unknown_plugin_exits_nonzero(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "targets: [does_not_exist]\nattacks: [static]\ndatasets: [demo]\n"
        "judges: [refusal_match]\nmetrics: [asr]"
    )
    result = runner.invoke(app, ["run", str(cfg), "--runs-dir", str(tmp_path / "runs")])
    assert result.exit_code == 1


def test_run_smoke_writes_report(tmp_path):
    result = runner.invoke(
        app, ["run", str(SMOKE_CONFIG), "--runs-dir", str(tmp_path / "runs")]
    )
    assert result.exit_code == 0
    assert (tmp_path / "runs" / "smoke" / "leaderboard.json").exists()


def test_run_malformed_config_exits_nonzero(tmp_path):
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("targets: [reference\n: : :")
    result = runner.invoke(app, ["run", str(cfg), "--runs-dir", str(tmp_path / "runs")])
    assert result.exit_code == 1


def test_main_maps_typed_error_to_exit_1(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "targets: [does_not_exist]\nattacks: [static]\ndatasets: [demo]\n"
        "judges: [refusal_match]\nmetrics: [asr]"
    )
    monkeypatch.setattr(
        "sys.argv", ["redharness", "run", str(cfg), "--runs-dir", str(tmp_path / "runs")]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "error:" in capsys.readouterr().err
