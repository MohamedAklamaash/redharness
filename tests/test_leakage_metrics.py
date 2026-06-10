"""Golden tests locking leakage metric values for fixed verdict sets."""

from __future__ import annotations

from redharness.core.models import Verdict
from redharness.metrics.leakage import (
    canary_exposure_rate,
    extraction_rate,
    pii_leak_rate,
    system_prompt_leak_rate,
    verbatim_overlap,
)
from tests.conftest import make_attempt, make_behavior


def _verdict(leaked: bool, overlap: float, category: str) -> Verdict:
    return Verdict(
        success=leaked,
        score=overlap,
        rubric={"leaked": leaked, "overlap": overlap, "category": category},
        judge_name="leak_detector",
    )


def _scored():
    """A canary (leaked), a pii (not leaked), a system_prompt (leaked)."""
    c = make_behavior(bid="c1", prompt="canary probe", category="canary")
    p = make_behavior(bid="p1", prompt="pii probe", category="pii")
    s = make_behavior(bid="s1", prompt="sysprompt probe", category="system_prompt")
    return [
        (c, make_attempt(c, "leaked canary"), _verdict(True, 1.0, "canary")),
        (p, make_attempt(p, "refused"), _verdict(False, 0.1, "pii")),
        (s, make_attempt(s, "leaked prompt"), _verdict(True, 1.0, "system_prompt")),
    ]


def test_extraction_rate_overall():
    # 2 of 3 probes leaked.
    assert extraction_rate.compute(_scored()).value == 2 / 3


def test_canary_exposure_rate_over_canary_only():
    result = canary_exposure_rate.compute(_scored())
    assert result.value == 1.0
    assert result.breakdown["n_probes"] == 1


def test_pii_leak_rate_over_pii_only():
    result = pii_leak_rate.compute(_scored())
    assert result.value == 0.0
    assert result.breakdown["n_probes"] == 1


def test_system_prompt_leak_rate_over_system_prompt_only():
    assert system_prompt_leak_rate.compute(_scored()).value == 1.0


def test_verbatim_overlap_is_mean_of_best_per_probe():
    # (1.0 + 0.1 + 1.0) / 3
    assert verbatim_overlap.compute(_scored()).value == round((1.0 + 0.1 + 1.0) / 3, 6)


def test_empty_suite_rates_and_overlap():
    # Overall extraction_rate and overlap are a genuine 0.0 over zero probes;
    # the per-category rates are N/A (None) because their subset is empty.
    assert extraction_rate.compute([]).value == 0.0
    assert verbatim_overlap.compute([]).value == 0.0
    assert canary_exposure_rate.compute([]).value is None
    assert pii_leak_rate.compute([]).value is None
    assert system_prompt_leak_rate.compute([]).value is None


def test_category_rate_na_when_category_absent():
    # A canary-only set leaves pii and system_prompt subsets empty -> N/A, not 0.0.
    c = make_behavior(bid="c1", prompt="canary probe", category="canary")
    scored = [(c, make_attempt(c, "leaked"), _verdict(True, 1.0, "canary"))]
    assert canary_exposure_rate.compute(scored).value == 1.0
    assert pii_leak_rate.compute(scored).value is None
    assert system_prompt_leak_rate.compute(scored).value is None


def test_probe_leaks_if_any_attempt_leaks():
    # Two attempts for one canary probe: one leaked, one not -> the probe counts
    # as leaked (the >=1-success aggregation convention).
    c = make_behavior(bid="c1", prompt="canary probe", category="canary")
    scored = [
        (c, make_attempt(c, "refused"), _verdict(False, 0.0, "canary")),
        (c, make_attempt(c, "leaked"), _verdict(True, 1.0, "canary")),
    ]
    assert canary_exposure_rate.compute(scored).value == 1.0
    # verbatim_overlap takes the best attempt per probe -> 1.0.
    assert verbatim_overlap.compute(scored).value == 1.0
