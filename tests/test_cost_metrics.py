"""Token-usage / cost metric tests: unit over synthetic usage + a mocked live run.

The unit half drives the metrics directly over hand-built ``(Behavior, Attempt,
Verdict)`` triples; the integration half runs a full :class:`Runner` against an
``httpx.MockTransport`` OpenAI target that reports ``usage`` and survives a 503 retry,
asserting (a) token totals across behaviors, (b) that a 503 (which carries no usage)
adds nothing, and (c) that a warm-cache re-run does not double-count and charges no new
usage. No network: everything is offline.
"""

from __future__ import annotations

import pytest

from redharness.config import RunConfig
from redharness.core.dataset import Dataset
from redharness.core.metric import ScoredAttempts
from redharness.core.models import Attempt, Behavior, Message, Verdict
from redharness.core.registry import register_dataset, register_target
from redharness.metrics.cost import cost, token_usage
from redharness.runner import Runner
from tests.conftest import make_behavior

# --- unit: metrics over synthetic per-behavior usage --------------------------


def _scored(*usages: dict | None) -> ScoredAttempts:
    out: ScoredAttempts = []
    for i, usage in enumerate(usages):
        behavior = make_behavior(bid=f"b{i}")
        metadata = {"usage": usage} if usage is not None else {}
        attempt = Attempt(
            behavior_id=behavior.id,
            attack_name="static",
            target_name="gpt-4o-mini-mock",
            transcript=[Message(role="user", content="x")],
            metadata=metadata,
        )
        verdict = Verdict(success=False, score=0.0, rubric={}, judge_name="j")
        out.append((behavior, attempt, verdict))
    return out


def test_token_usage_sums_input_and_output_across_behaviors():
    scored = _scored(
        {"input_tokens": 10, "output_tokens": 5},
        {"input_tokens": 7, "output_tokens": 3},
    )
    result = token_usage.compute(scored)
    assert result.value == 25.0
    assert result.breakdown["input_tokens"] == 17
    assert result.breakdown["output_tokens"] == 8
    assert result.breakdown["n_behaviors"] == 2


def test_token_usage_is_na_when_no_attempt_carries_usage():
    result = token_usage.compute(_scored(None, None))
    assert result.value is None  # offline/local runs report N/A, not 0


def test_usage_counted_once_per_behavior_with_multiple_attempts():
    behavior = make_behavior(bid="b0")
    usage = {"input_tokens": 4, "output_tokens": 2}
    attempts = [
        Attempt(
            behavior_id=behavior.id,
            attack_name="static",
            target_name="t",
            transcript=[Message(role="user", content="x")],
            metadata={"usage": usage},
        )
        for _ in range(3)
    ]
    verdict = Verdict(success=False, score=0.0, rubric={}, judge_name="j")
    scored = [(behavior, a, verdict) for a in attempts]
    assert token_usage.compute(scored).breakdown["total_tokens"] == 6  # not 18


def test_cost_prices_known_model_and_is_na_for_unpriced():
    priced = cost.compute(_scored({"input_tokens": 1_000_000, "output_tokens": 1_000_000}))
    assert priced.value is not None and priced.value > 0
    assert priced.breakdown["n_priced"] == 1
    assert priced.breakdown["price_table_date"]

    behavior = make_behavior()
    attempt = Attempt(
        behavior_id=behavior.id,
        attack_name="static",
        target_name="some-local-llama",  # not in the price table
        transcript=[Message(role="user", content="x")],
        metadata={"usage": {"input_tokens": 10, "output_tokens": 5}},
    )
    verdict = Verdict(success=False, score=0.0, rubric={}, judge_name="j")
    unpriced = cost.compute([(behavior, attempt, verdict)])
    assert unpriced.value is None  # priced nothing -> N/A, not a misleading $0
    assert "some-local-llama" in unpriced.breakdown["unpriced"]


def test_cost_is_na_offline():
    assert cost.compute(_scored(None)).value is None


# --- integration: a mocked multi-call run stamps and tallies usage ------------

httpx = pytest.importorskip("httpx")

from redharness.targets import _http  # noqa: E402
from redharness.targets.openai_compat import OpenAICompatTarget  # noqa: E402

_USAGE = {"prompt_tokens": 10, "completion_tokens": 5}


@register_dataset("_cost_tiny_ds")
class _CostTinyDataset(Dataset):
    name = "_cost_tiny_ds"

    @property
    def version(self) -> str:
        return "_cost_tiny@0"

    def load(self) -> list[Behavior]:
        return [
            Behavior(id=f"c{i}", prompt=f"benign {i}", category="c", expected="should_refuse")
            for i in range(3)
        ]


class _CostState:
    first_call_503 = True


def _cost_handler(request):
    if _CostState.first_call_503:
        _CostState.first_call_503 = False
        return httpx.Response(503, json={"error": "unavailable"})  # carries no usage
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "Sure, here is a benign answer."}}],
            "usage": _USAGE,
        },
    )


@register_target("_cost_openai")
class _CostOpenAITarget(OpenAICompatTarget):
    def __init__(self, name: str | None = None) -> None:
        super().__init__(
            model="gpt-4o-mini",
            name=name or "gpt-4o-mini-mock",  # substring matches the price table
            base_url="https://api.test/v1",
            api_key_env="REDHARNESS_OPENAI_API_KEY",
            transport=httpx.MockTransport(_cost_handler),
            max_retries=2,
        )


def _cost_config() -> RunConfig:
    return RunConfig.model_validate(
        {
            "run_name": "cost",
            "targets": [{"name": "_cost_openai"}],
            "attacks": [{"name": "static"}],  # one provider call per behavior
            "datasets": [{"name": "_cost_tiny_ds"}],
            "judges": [{"name": "refusal_match"}],
            "metrics": ["asr", "token_usage", "cost"],
        }
    )


@pytest.fixture(autouse=True)
def _instant_backoff_and_key(monkeypatch):
    monkeypatch.setattr(_http, "_backoff_seconds", lambda *a, **k: 0.0)
    monkeypatch.setenv("REDHARNESS_OPENAI_API_KEY", "sk-test")
    _CostState.first_call_503 = True


def test_run_tallies_token_usage_across_behaviors_503_carries_none(tmp_path):
    runner = Runner(_cost_config(), tmp_path)
    result = runner.run()
    [cell] = result.cells

    tokens = cell.metrics["token_usage"]
    # 3 behaviors x one successful 200 (10 in / 5 out); the leading 503 added nothing.
    assert tokens.breakdown["input_tokens"] == 30
    assert tokens.breakdown["output_tokens"] == 15
    assert tokens.value == 45.0
    assert cell.metrics["cost"].value is not None  # gpt-4o-mini is priceable
    # The run-wide tally counted exactly the 3 usage-bearing calls (not the 503).
    assert runner.budget.usage.calls == 3


def test_warm_cache_rerun_does_not_double_count_or_recharge_usage(tmp_path):
    Runner(_cost_config(), tmp_path).run()  # cold: warms the cache

    _CostState.first_call_503 = False  # would all be 200s, but cache hits make no call
    runner2 = Runner(_cost_config(), tmp_path)
    result = runner2.run()
    [cell] = result.cells

    # Cached attempts keep their stamped usage -> the metric still reports 45, not 90.
    assert cell.metrics["token_usage"].value == 45.0
    # ...and no real provider call happened on the warm run, so nothing was re-charged.
    assert runner2.budget.usage.calls == 0
    assert runner2.budget.spent == 0
