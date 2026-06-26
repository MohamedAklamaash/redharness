"""Pure statistical helpers: Cohen's kappa and a seeded bootstrap CI.

These are dependency-free, deterministic functions used by the judge-agreement
analysis (Cohen 1960) and by the rate metrics' confidence intervals (Efron's
bootstrap). They take plain values and never touch a model, the network, or the
wall clock, so they are unit-testable in isolation and reproducible.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence


def cohen_kappa(labels_a: Sequence[bool], labels_b: Sequence[bool]) -> float:
    """Cohen's kappa for two raters' binary labels over the same items.

    ``kappa = (p_o - p_e) / (1 - p_e)`` where ``p_o`` is the observed agreement and
    ``p_e`` the agreement expected by chance from each rater's marginals. Returns
    ``1.0`` for perfect agreement, ``~0.0`` for chance-level agreement, and a
    negative value for systematic disagreement. When chance agreement is total
    (``p_e == 1``, e.g. both raters label every item identically), kappa is defined
    as ``1.0`` if the raters fully agree and ``0.0`` otherwise — avoiding a 0/0.
    """
    if len(labels_a) != len(labels_b):
        raise ValueError("cohen_kappa requires equal-length label sequences")
    n = len(labels_a)
    if n == 0:
        return 0.0
    observed = sum(1 for a, b in zip(labels_a, labels_b, strict=True) if a == b) / n
    a_true = sum(labels_a) / n
    b_true = sum(labels_b) / n
    expected = a_true * b_true + (1 - a_true) * (1 - b_true)
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float] = _mean,
    n_resamples: int = 1000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float] | tuple[None, None]:
    """Percentile bootstrap confidence interval for ``statistic`` over ``values``.

    Resamples ``values`` with replacement ``n_resamples`` times under a fixed
    ``seed`` (so the interval is fully deterministic), evaluates ``statistic`` on
    each resample, and returns the lower/upper percentile bounds for the requested
    two-sided ``confidence`` level. An empty input yields ``(None, None)``; a single
    value (or all-identical values) yields a degenerate zero-width interval at that
    value. ``confidence`` must be in ``(0, 1)``.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in the open interval (0, 1)")
    if n_resamples < 1:
        raise ValueError("n_resamples must be >= 1")
    n = len(values)
    if n == 0:
        return (None, None)
    rng = random.Random(seed)
    stats = sorted(
        statistic([values[rng.randrange(n)] for _ in range(n)])
        for _ in range(n_resamples)
    )
    alpha = (1.0 - confidence) / 2.0
    lo_index = int(alpha * n_resamples)
    hi_index = min(n_resamples - 1, int((1.0 - alpha) * n_resamples))
    return (stats[lo_index], stats[hi_index])


#: Fixed bootstrap seed for the rate-metric CIs. The per-behavior outcomes are
#: themselves deterministic, so a constant seed keeps the reported interval stable
#: across identical runs (the metric layer has no access to the run seed).
RATE_CI_SEED = 1729


def rate_ci(outcomes: Sequence[bool]) -> tuple[float | None, float | None]:
    """A deterministic 95% bootstrap CI over per-behavior 0/1 outcomes.

    Returns ``(None, None)`` for fewer than two outcomes (an interval would be
    degenerate / uninformative), else the rounded percentile bounds of the mean.
    """
    if len(outcomes) < 2:
        return (None, None)
    lo, hi = bootstrap_ci([1.0 if o else 0.0 for o in outcomes], seed=RATE_CI_SEED)
    if lo is None or hi is None:
        return (None, None)
    return (round(lo, 6), round(hi, 6))
