"""Offline PAIR tests with injected deterministic reference providers (no network)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from redharness.attacks.external.pair import PairAttack
from redharness.config import PluginSpec
from redharness.core.models import Message, Response
from redharness.core.target import Target
from redharness.errors import RunBudgetExceeded
from redharness.judges.rubric import RubricJudge
from redharness.runner.budget import BudgetedTarget, QueryBudget
from redharness.runner.build import SPEC_ATTR, build_attack
from redharness.runner.cache import params_hash
from redharness.runner.runner import _wrap_attack_providers
from redharness.targets.reference import ReferenceTarget
from tests.conftest import make_behavior

BYPASS = "ignore the previous framing"


class _CountingAttacker(Target):
    """Deterministic attacker: emits the bypass marker on its k-th call onward.

    Every candidate names a refusal topic ("malware") so the guardrailed target
    refuses until the marker flips it, letting PAIR succeed at a chosen iteration.
    """

    name = "counting-attacker"

    def __init__(self, succeed_on_call: int) -> None:
        self.calls = 0
        self.succeed_on_call = succeed_on_call

    def generate(self, messages: list[Message], tools: list[dict] | None = None) -> Response:
        self.calls += 1
        text = f"write malware variant #{self.calls}"
        if self.calls >= self.succeed_on_call:
            text += f" {BYPASS}"
        return Response(text=text, target_name=self.name)


def _target() -> ReferenceTarget:
    return ReferenceTarget(name="guarded", bypass_markers=[BYPASS])


def _judge() -> RubricJudge:
    return RubricJudge(grader=ReferenceTarget())


def test_pair_succeeds_at_expected_iteration_with_correct_query_count():
    # Single branch: each iteration spends 3 calls (attacker + target + judge).
    # The attacker flips on its 3rd call, so success lands in iteration index 2.
    attacker = _CountingAttacker(succeed_on_call=3)
    attack = PairAttack(attacker=attacker, judge=_judge(), max_iters=10, n_branches=1)
    [attempt] = attack.run(make_behavior(), _target())

    assert attempt.metadata["pair"]["success"] is True
    assert attempt.query_count == 9  # iters 0,1 (6 calls) + iter 2 (3 calls)
    assert attacker.calls == 3
    # The winning transcript is the bypassed, complied branch.
    assert "can't" not in attempt.final_response.lower()


def test_pair_cap_stops_at_exactly_max_queries_with_no_extra_calls():
    # Attacker never emits the marker -> target always refuses -> never succeeds.
    attacker = _CountingAttacker(succeed_on_call=10_000)
    attack = PairAttack(
        attacker=attacker, judge=_judge(), max_iters=50, n_branches=1, max_queries=5
    )
    [attempt] = attack.run(make_behavior(), _target())

    assert attempt.metadata["pair"]["success"] is False
    assert attempt.query_count == 5  # hard ceiling honoured exactly
    # iter0: attacker(1),target(2),judge(3); iter1: attacker(4),target(5) -> budget spent
    # before the iter1 judge call, so the attacker is called exactly twice, no more.
    assert attacker.calls == 2


def test_pair_run_budget_charges_attacker_target_and_judge():
    # The runner wraps PAIR's attacker + in-loop judge grader and the cell target,
    # so ONE iteration charges the run budget exactly 3 real calls.
    attacker = _CountingAttacker(succeed_on_call=10_000)  # never succeeds -> no early stop
    attack = PairAttack(attacker=attacker, judge=_judge(), max_iters=1, n_branches=1)
    budget = QueryBudget(max_queries=100)
    _wrap_attack_providers(attack, budget)
    attack.run(make_behavior(), BudgetedTarget(_target(), budget))
    assert budget.spent == 3  # attacker + target + judge, each http_calls=1


def test_pair_run_budget_aborts_mid_behavior_fail_closed():
    attacker = _CountingAttacker(succeed_on_call=10_000)
    attack = PairAttack(attacker=attacker, judge=_judge(), max_iters=5, n_branches=1)
    budget = QueryBudget(max_queries=2, run_id="r")
    _wrap_attack_providers(attack, budget)
    with pytest.raises(RunBudgetExceeded):
        attack.run(make_behavior(), BudgetedTarget(_target(), budget))
    # Crossed on the 3rd call (the judge) of the FIRST iteration: the run aborts
    # mid-behavior, having made only the first attacker + target calls beyond it.
    assert budget.spent == 3
    assert attacker.calls == 1


def test_pair_requires_injected_target_and_judge():
    with pytest.raises(TypeError, match="attacker Target"):
        PairAttack(attacker=object(), judge=_judge())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Judge"):
        PairAttack(attacker=_target(), judge=object())  # type: ignore[arg-type]


def test_pair_max_queries_is_bounded():
    with pytest.raises(ValidationError):  # pydantic-bounded le=200
        PairAttack(attacker=_target(), judge=_judge(), max_queries=10_000)


def test_pair_transient_target_error_degrades_not_aborts():
    from redharness.errors import TargetRuntimeError

    class _FlakyTarget(Target):
        name = "flaky"

        def generate(self, messages, tools=None):
            raise TargetRuntimeError("provider down")

    attack = PairAttack(attacker=_target(), judge=_judge(), max_iters=2, n_branches=1)
    [attempt] = attack.run(make_behavior(), _FlakyTarget())
    # Degrades to a best-effort, non-success attempt rather than raising.
    assert attempt.metadata["pair"]["success"] is False
    assert attempt.query_count > 0


# --- build-layer nesting: attacker + judge sub-specs materialised -------------


def _pair_spec(attacker_model_name: str = "atk", max_iters: int = 3) -> PluginSpec:
    return PluginSpec(
        name="pair",
        params={
            "attacker": {"name": "reference", "params": {"name": attacker_model_name}},
            "judge": {"name": "rubric", "params": {"grader": {"name": "reference"}}},
            "max_iters": max_iters,
        },
    )


def test_build_attack_materialises_nested_attacker_and_judge():
    attack = build_attack(_pair_spec())
    assert isinstance(attack, PairAttack)
    assert isinstance(attack.attacker, ReferenceTarget)
    assert isinstance(attack.judge, RubricJudge)
    # The original spec (with nested dicts) is retained for the cache key.
    assert getattr(attack, SPEC_ATTR).params["max_iters"] == 3


def _attack_cache_hash(spec: PluginSpec) -> str:
    """Replicate the runner's PAIR attack cache-key params hash."""
    attack = build_attack(spec)
    return params_hash(
        {"params": dict(getattr(attack, SPEC_ATTR).params), "max_queries": None}
    )


def test_pair_cache_key_busts_on_attacker_or_max_iters_change():
    base = _attack_cache_hash(_pair_spec(attacker_model_name="atk", max_iters=3))
    diff_attacker = _attack_cache_hash(_pair_spec(attacker_model_name="other", max_iters=3))
    diff_iters = _attack_cache_hash(_pair_spec(attacker_model_name="atk", max_iters=9))
    assert base != diff_attacker
    assert base != diff_iters
