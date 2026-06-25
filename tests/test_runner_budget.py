"""Runner-level tests: error tolerance, run budget, and secret non-leakage.

All offline: live adapters are driven through httpx.MockTransport and the rest of
the matrix uses injected reference/deterministic plugins.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from redharness.config import RunConfig
from redharness.core.dataset import Dataset
from redharness.core.models import Behavior, Message, Response
from redharness.core.registry import register_dataset, register_target
from redharness.core.target import Target
from redharness.errors import RunBudgetExceeded, TargetRuntimeError
from redharness.report import write_reports
from redharness.runner import Runner
from redharness.runner.budget import BudgetedTarget, QueryBudget

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


# --- C: error-tolerant runner -------------------------------------------------


class _FlakyState:
    raise_on_trigger = True


@register_dataset("_budget_tiny_ds")
class _TinyDataset(Dataset):
    name = "_budget_tiny_ds"

    @property
    def version(self) -> str:
        return "_tiny@0"

    def load(self) -> list[Behavior]:
        return [
            Behavior(id="ok1", prompt="benign one", category="c", expected="should_refuse"),
            Behavior(id="boom", prompt="TRIGGER ERROR", category="c", expected="should_refuse"),
            Behavior(id="ok2", prompt="benign two", category="c", expected="should_refuse"),
        ]


@register_target("_flaky_target")
class _FlakyTarget(Target):
    name = "_flaky_target"

    def __init__(self, name: str | None = None) -> None:
        self.name = name or "_flaky_target"

    def generate(self, messages, tools=None):
        text = " ".join(m.content for m in messages)
        if _FlakyState.raise_on_trigger and "TRIGGER ERROR" in text:
            raise TargetRuntimeError("boom on this behavior")
        return Response(text="Sure, here is help.", target_name=self.name)


def _flaky_config() -> RunConfig:
    return RunConfig.model_validate(
        {
            "run_name": "flaky",
            "targets": [{"name": "_flaky_target"}],
            "attacks": [{"name": "static"}],
            "datasets": [{"name": "_budget_tiny_ds"}],
            "judges": [{"name": "refusal_match"}],
            "metrics": ["asr"],
        }
    )


def test_runner_continues_on_attack_error_and_records_errored_attempt(tmp_path):
    _FlakyState.raise_on_trigger = True
    runner = Runner(_flaky_config(), tmp_path)
    result = runner.run()  # must NOT raise despite the boom behavior
    assert result.cells

    rows = _read_jsonl(runner.transcript_path)
    by_id = {r["behavior_id"]: r for r in rows}
    assert by_id["boom"]["metadata"].get("errored") is True
    assert by_id["ok1"]["metadata"].get("errored") is None  # healthy behaviors are fine


def test_errored_attempt_is_not_cached_as_success(tmp_path):
    # Run 1 errors on "boom" (not cached). Run 2 with the target healed must
    # re-run "boom" (cache miss) and produce a real, non-errored attempt.
    _FlakyState.raise_on_trigger = True
    Runner(_flaky_config(), tmp_path).run()

    _FlakyState.raise_on_trigger = False
    runner2 = Runner(_flaky_config(), tmp_path)
    runner2.run()
    rows = {r["behavior_id"]: r for r in _read_jsonl(runner2.transcript_path)}
    assert rows["boom"]["metadata"].get("errored") is None
    assert rows["boom"]["transcript"][-1]["content"] == "Sure, here is help."


@register_target("_long_error_target")
class _LongErrorTarget(Target):
    name = "_long_error_target"

    def __init__(self, name: str | None = None) -> None:
        self.name = name or "_long_error_target"

    def generate(self, messages, tools=None):
        # A catch-all (non-RedharnessError) failure with an oversized payload: the
        # runner must persist a sanitized, length-capped error, not the raw blob.
        raise RuntimeError("X" * 5000)


def test_persisted_error_string_is_truncated_and_run_continues(tmp_path):
    cfg = RunConfig.model_validate(
        {
            "run_name": "longerr",
            "targets": [{"name": "_long_error_target"}],
            "attacks": [{"name": "static"}],
            "datasets": [{"name": "_budget_tiny_ds"}],
            "judges": [{"name": "refusal_match"}],
            "metrics": ["asr"],
        }
    )
    runner = Runner(cfg, tmp_path)
    result = runner.run()  # must NOT raise despite every behavior erroring
    assert result.cells

    rows = _read_jsonl(runner.transcript_path)
    assert rows  # the run continued and recorded errored attempts
    for row in rows:
        error = row["metadata"]["error"]
        assert row["metadata"]["errored"] is True
        assert error.startswith("RuntimeError: ")
        assert len(error) < 300  # capped, not the full 5000-char payload
        assert error.endswith("...(truncated)")


# --- C: run budget ------------------------------------------------------------


def test_run_budget_exceeded_aborts_with_typed_error(tmp_path):
    cfg = RunConfig.model_validate(
        {
            "run_name": "budget",
            "max_queries": 2,  # the 3-behavior tiny dataset spends 3 queries
            "targets": [{"name": "_flaky_target"}],
            "attacks": [{"name": "static"}],
            "datasets": [{"name": "_budget_tiny_ds"}],
            "judges": [{"name": "refusal_match"}],
            "metrics": ["asr"],
        }
    )
    _FlakyState.raise_on_trigger = False
    with pytest.raises(RunBudgetExceeded, match="budget"):
        Runner(cfg, tmp_path).run()


def test_query_budget_charges_and_fails_closed_at_ceiling():
    budget = QueryBudget(max_queries=3, run_id="x")
    budget.charge(2)
    assert budget.spent == 2
    budget.charge(1)  # exactly at the ceiling: still ok
    assert budget.spent == 3
    with pytest.raises(RunBudgetExceeded, match="budget"):
        budget.charge(1)  # crossing the ceiling fails closed


def test_query_budget_none_is_unbounded():
    budget = QueryBudget(max_queries=None)
    budget.charge(10_000)  # never raises
    assert budget.spent == 10_000


def test_run_budget_aborts_mid_behavior_without_finishing(tmp_path):
    # The template attack issues 3 provider calls per behavior. With max_queries=2,
    # the budget is crossed on the 3rd call of the FIRST behavior, so the run aborts
    # mid-behavior: that behavior never completes and NOTHING is written for it
    # (the old per-behavior charging would have finished the behavior first).
    cfg = RunConfig.model_validate(
        {
            "run_name": "midbehavior",
            "max_queries": 2,
            "targets": [{"name": "reference"}],
            "attacks": [{"name": "template"}],  # 3 calls per behavior
            "datasets": [{"name": "_budget_tiny_ds"}],
            "judges": [{"name": "refusal_match"}],
            "metrics": ["asr"],
        }
    )
    _FlakyState.raise_on_trigger = False
    runner = Runner(cfg, tmp_path)
    with pytest.raises(RunBudgetExceeded):
        runner.run()
    assert _read_jsonl(runner.transcript_path) == []  # aborted before any attempt


def test_warm_cache_rerun_does_not_charge_budget(tmp_path):
    # Cache HITS are real-call-free, so a warm-cache re-run charges nothing and never
    # aborts — even though the same budget would be fully spent on a cold run.
    cfg_dict = {
        "run_name": "warm",
        "max_queries": 3,  # exactly the 3 cold-run calls; a 4th would fail closed
        "targets": [{"name": "reference"}],
        "attacks": [{"name": "static"}],
        "datasets": [{"name": "_budget_tiny_ds"}],  # 3 behaviors
        "judges": [{"name": "refusal_match"}],
        "metrics": ["asr"],
    }
    _FlakyState.raise_on_trigger = False
    Runner(RunConfig.model_validate(cfg_dict), tmp_path).run()  # cold: warms the cache

    runner2 = Runner(RunConfig.model_validate(cfg_dict), tmp_path)
    result = runner2.run()  # warm: every behavior is a cache hit
    assert result.cells  # completes, never aborts
    assert runner2.budget.spent == 0  # no real provider call -> no charge


def test_max_queries_is_pydantic_bounded():
    with pytest.raises(ValidationError):  # pydantic-bounded le
        RunConfig.model_validate(
            {
                "run_name": "x",
                "max_queries": 99_999_999_999,
                "targets": [{"name": "reference"}],
                "attacks": [{"name": "static"}],
                "datasets": [{"name": "demo"}],
                "judges": [{"name": "refusal_match"}],
                "metrics": ["asr"],
            }
        )


# --- C1: the API key never leaks into any artifact ----------------------------

httpx = pytest.importorskip("httpx")

from redharness.targets import _http  # noqa: E402
from redharness.targets.openai_compat import (  # noqa: E402
    API_KEY_ENV,
    OpenAICompatTarget,
)


def test_http_calls_counts_retries_and_budget_charges_them(monkeypatch):
    # A target that returns 503 -> 503 -> 200 makes 3 real HTTP calls; http_calls
    # reflects that, and the budget is charged exactly 3 (not 1 per logical call).
    monkeypatch.setenv(API_KEY_ENV, "sk-x")
    monkeypatch.setattr(_http, "_backoff_seconds", lambda *a, **k: 0.0)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    target = OpenAICompatTarget(
        model="gpt-test",
        base_url="https://api.test/v1",
        transport=httpx.MockTransport(handler),
        max_retries=2,
    )
    budget = QueryBudget(max_queries=10)
    resp = BudgetedTarget(target, budget).generate([Message(role="user", content="hi")])

    assert resp.text == "ok"
    assert resp.http_calls == 3  # 503, 503, 200
    assert calls["n"] == 3
    assert budget.spent == 3  # the retry-inclusive real-call count, charged once


SENTINEL = "sk-LEAK-CANARY-9f8e7d6c5b4a"
_CAPTURED: dict[str, str] = {}


def _leak_handler(request):
    _CAPTURED["authorization"] = request.headers.get("authorization", "")
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "Sure, here is a benign answer."}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
    )


@register_target("_mock_openai_leak")
class _MockOpenAILeakTarget(OpenAICompatTarget):
    def __init__(self, name: str | None = None) -> None:
        super().__init__(
            model="gpt-test",
            name=name or "mock-openai",
            base_url="https://api.test/v1",
            transport=httpx.MockTransport(_leak_handler),
        )


def test_api_key_never_appears_in_transcripts_cache_or_leaderboard(tmp_path, monkeypatch):
    monkeypatch.setenv("REDHARNESS_OPENAI_API_KEY", SENTINEL)
    cfg = RunConfig.model_validate(
        {
            "run_name": "leakcheck",
            "targets": [{"name": "_mock_openai_leak"}],
            "attacks": [{"name": "static"}],
            "datasets": [{"name": "_budget_tiny_ds"}],
            "judges": [{"name": "refusal_match"}],
            "metrics": ["asr"],
        }
    )
    runner = Runner(cfg, tmp_path)
    result = runner.run()
    paths = write_reports(result, runner.run_dir)

    # The key WAS sent over the wire (proving the adapter used it)...
    assert SENTINEL in _CAPTURED["authorization"]

    # ...but it must appear in NONE of the persisted artifacts.
    artifacts = [runner.transcript_path, paths["leaderboard"]]
    artifacts += list((runner.run_dir / "cache").glob("*.json"))
    for path in artifacts:
        assert SENTINEL not in Path(path).read_text(), f"sentinel leaked into {path}"


# --- Offline core: imports + smoke runs with httpx (the extras dep) blocked ----


def test_offline_core_runs_without_httpx_installed():
    # Simulate neither the 'openai' nor 'anthropic' extra being installed by making
    # `import httpx` fail in a fresh interpreter, then proving the package imports
    # and the jailbreak smoke config still runs end to end.
    script = (
        "import sys; sys.modules['httpx'] = None\n"
        "import tempfile, pathlib\n"
        "import redharness.plugins\n"
        "from redharness.config import load_config\n"
        "from redharness.runner import Runner\n"
        "cfg = load_config('configs/smoke.yaml')\n"
        "res = Runner(cfg, pathlib.Path(tempfile.mkdtemp())).run()\n"
        "assert res.cells, 'no cells produced'\n"
        "print('OFFLINE_OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OFFLINE_OK" in proc.stdout
