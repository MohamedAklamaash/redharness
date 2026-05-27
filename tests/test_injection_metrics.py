"""Golden tests locking the injection metric values for fixed verdict sets."""

from __future__ import annotations

from redharness.core.models import Verdict
from redharness.metrics.injection import (
    injection_success_rate,
    utility_baseline,
    utility_under_attack,
)
from tests.conftest import make_attempt, make_behavior


def _verdict(attacker: bool, utility: bool, injected: bool) -> Verdict:
    return Verdict(
        success=attacker,
        score=1.0 if attacker else 0.0,
        rubric={
            "attacker_succeeded": attacker,
            "user_task_completed": utility,
            "injected": injected,
        },
        judge_name="injection_detector",
    )


def _scored():
    """Two injected scenarios (one hijacked, one not) + one no-injection baseline."""
    s1 = make_behavior(bid="s1", prompt="task one", category="suite", expected="should_refuse")
    s2 = make_behavior(bid="s2", prompt="task two", category="suite", expected="should_refuse")
    base = make_behavior(bid="b1", prompt="task base", category="suite", expected="should_refuse")
    return [
        (s1, make_attempt(s1, "done"), _verdict(attacker=True, utility=True, injected=True)),
        (s2, make_attempt(s2, "done"), _verdict(attacker=False, utility=True, injected=True)),
        (base, make_attempt(base, "done"), _verdict(attacker=False, utility=True, injected=False)),
    ]


def test_isr_counts_one_of_two_injected():
    result = injection_success_rate.compute(_scored())
    assert result.value == 0.5
    assert result.breakdown["n_scenarios"] == 2


def test_utility_under_attack_over_injected_only():
    result = utility_under_attack.compute(_scored())
    # both injected scenarios completed the task -> 1.0 over the injected subset
    assert result.value == 1.0
    assert result.breakdown["n_scenarios"] == 2


def test_utility_baseline_over_non_injected_only():
    result = utility_baseline.compute(_scored())
    # one baseline scenario, completed -> 1.0 over the one non-injected scenario
    assert result.value == 1.0
    assert result.breakdown["n_scenarios"] == 1


def test_injection_metrics_on_empty_input():
    # ISR over no scenarios is a genuine 0.0; the utility metrics are not
    # applicable to an empty subset and report N/A (None), not a misleading 0.0.
    assert injection_success_rate.compute([]).value == 0.0
    assert utility_under_attack.compute([]).value is None
    assert utility_baseline.compute([]).value is None


def test_isr_zero_when_no_injected_scenarios():
    base = make_behavior(bid="b1", prompt="t", category="s", expected="should_refuse")
    scored = [(base, make_attempt(base, "x"), _verdict(False, True, injected=False))]
    assert injection_success_rate.compute(scored).value == 0.0
    # No injected scenarios -> utility_under_attack does not apply to this cell.
    assert utility_under_attack.compute(scored).value is None
    assert utility_baseline.compute(scored).value == 1.0


def test_utility_baseline_na_when_all_injected():
    # An all-injected set has an empty baseline subset -> utility_baseline is N/A.
    inj = make_behavior(bid="s1", prompt="t", category="s", expected="should_refuse")
    scored = [(inj, make_attempt(inj, "x"), _verdict(True, True, injected=True))]
    assert utility_baseline.compute(scored).value is None
    assert utility_under_attack.compute(scored).value == 1.0
