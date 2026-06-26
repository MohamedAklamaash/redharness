"""Rate metrics carry an additive, deterministic bootstrap CI around their value."""

from __future__ import annotations

from redharness.core.models import Verdict
from redharness.metrics.core import asr, frr
from tests.conftest import make_attempt, make_behavior


def _scored(expected: str, successes: list[bool]):
    rows = []
    for index, success in enumerate(successes):
        behavior = make_behavior(bid=f"b{index}", expected=expected)
        attempt = make_attempt(behavior, "x")
        verdict = Verdict(success=success, score=1.0 if success else 0.0, judge_name="t")
        rows.append((behavior, attempt, verdict))
    return rows


def test_asr_value_unchanged_and_ci_present_and_deterministic():
    scored = _scored("should_refuse", [True, True, False, False, True])
    result = asr.compute(scored)
    again = asr.compute(scored)
    assert result.value == 0.6
    assert result.ci_low is not None and result.ci_high is not None
    assert result.ci_low <= result.value <= result.ci_high
    assert (result.ci_low, result.ci_high) == (again.ci_low, again.ci_high)


def test_single_behavior_has_degenerate_none_ci():
    result = asr.compute(_scored("should_refuse", [True]))
    assert result.value == 1.0
    assert result.ci_low is None and result.ci_high is None


def test_frr_carries_ci():
    result = frr.compute(_scored("should_comply", [False, False, True, True]))
    # benign refused == not success; two of four refused -> frr 0.5.
    assert result.value == 0.5
    assert result.ci_low is not None and result.ci_high is not None
