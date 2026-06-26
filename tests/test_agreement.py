"""Unit tests for the pure stats helpers: Cohen's kappa and the bootstrap CI."""

from __future__ import annotations

import pytest

from redharness.metrics.agreement import bootstrap_ci, cohen_kappa, rate_ci


def test_cohen_kappa_perfect_agreement_is_one():
    labels = [True, False, True, False, True]
    assert cohen_kappa(labels, labels) == 1.0


def test_cohen_kappa_chance_agreement_is_about_zero():
    # po = 0.5, pe = 0.5  ->  kappa = 0 exactly.
    a = [True, True, False, False]
    b = [True, False, True, False]
    assert cohen_kappa(a, b) == pytest.approx(0.0)


def test_cohen_kappa_total_disagreement_is_negative():
    a = [True, False, True, False]
    b = [False, True, False, True]
    assert cohen_kappa(a, b) == pytest.approx(-1.0)
    assert cohen_kappa(a, b) < 0


def test_cohen_kappa_degenerate_constant_raters():
    # Both raters label everything True: chance agreement is total (pe == 1).
    assert cohen_kappa([True, True, True], [True, True, True]) == 1.0


def test_cohen_kappa_empty_and_length_mismatch():
    assert cohen_kappa([], []) == 0.0
    with pytest.raises(ValueError, match="equal-length"):
        cohen_kappa([True], [True, False])


def test_bootstrap_ci_empty_is_none():
    assert bootstrap_ci([]) == (None, None)


def test_bootstrap_ci_identical_values_is_degenerate():
    assert bootstrap_ci([0.5, 0.5, 0.5], seed=0) == (0.5, 0.5)
    assert bootstrap_ci([1.0], seed=7) == (1.0, 1.0)


def test_bootstrap_ci_is_seeded_and_reproducible():
    values = [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    first = bootstrap_ci(values, seed=1729)
    second = bootstrap_ci(values, seed=1729)
    assert first == second
    lo, hi = first
    assert 0.0 <= lo <= 0.6 <= hi <= 1.0


def test_bootstrap_ci_validates_confidence():
    with pytest.raises(ValueError, match="confidence"):
        bootstrap_ci([0.0, 1.0], confidence=1.5)


def test_rate_ci_needs_two_outcomes():
    assert rate_ci([True]) == (None, None)
    lo, hi = rate_ci([True, True, False, False])
    assert lo is not None and hi is not None and lo <= hi
