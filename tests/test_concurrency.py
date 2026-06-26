"""Opt-in bounded concurrency: identical results to the sequential path + fail-close.

A reference matrix is run at concurrency 1 and 4; the leaderboard values and the
transcript bytes must be identical (deterministic order regardless of completion
order). The run budget must still fail-close under concurrency.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from redharness.config import RunConfig
from redharness.errors import RunBudgetExceeded
from redharness.report import write_reports
from redharness.report.render import build_leaderboard
from redharness.runner import Runner


def _config(run_name: str, concurrency: int, max_queries: int | None = None) -> RunConfig:
    payload = {
        "run_name": run_name,
        "concurrency": concurrency,
        "targets": [
            {"name": "reference", "params": {"name": "aligned-reference"}},
            {"name": "reference", "params": {"name": "permissive-reference",
                                             "refusal_topics": ["ransomware"]}},
        ],
        "attacks": [{"name": "static"}, {"name": "template"}],
        "datasets": [{"name": "demo"}],
        "judges": [{"name": "refusal_match"}],
        "metrics": ["asr", "refusal_rate", "frr"],
    }
    if max_queries is not None:
        payload["max_queries"] = max_queries
    return RunConfig.model_validate(payload)


def test_concurrency_matches_sequential_leaderboard(tmp_path):
    seq = Runner(_config("seq", concurrency=1), tmp_path / "a").run()
    par = Runner(_config("par", concurrency=4), tmp_path / "b").run()

    def _values(result):
        return sorted(
            (r["attack"], r["target"], r["metric"], r["value"])
            for r in build_leaderboard(result)
        )

    assert _values(seq) == _values(par)


def test_concurrency_transcripts_are_byte_identical(tmp_path):
    r1 = Runner(_config("smoke", concurrency=1), tmp_path / "c1")
    r1.run()
    write_reports_path1 = Path(r1.transcript_path).read_text()

    r4 = Runner(_config("smoke", concurrency=4), tmp_path / "c4")
    r4.run()
    write_reports_path4 = Path(r4.transcript_path).read_text()

    assert write_reports_path1 == write_reports_path4


def test_concurrency_leaderboard_artifacts_match(tmp_path):
    r1 = Runner(_config("smoke", concurrency=1), tmp_path / "d1")
    res1 = r1.run()
    p1 = write_reports(res1, r1.run_dir)
    r4 = Runner(_config("smoke", concurrency=4), tmp_path / "d4")
    res4 = r4.run()
    p4 = write_reports(res4, r4.run_dir)
    assert p1["leaderboard"].read_text() == p4["leaderboard"].read_text()


def test_budget_fails_closed_under_concurrency(tmp_path):
    # The full reference matrix spends well over 5 real calls; with a budget of 5 and
    # 4 workers the run must still abort fail-closed with the typed error.
    cfg = _config("budget", concurrency=4, max_queries=5)
    with pytest.raises(RunBudgetExceeded):
        Runner(cfg, tmp_path).run()
