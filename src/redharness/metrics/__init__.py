"""Metric plugins. Importing this package registers the built-in metrics."""

from redharness.metrics.core import (
    asr,
    asr_at_k,
    frr,
    refusal_rate,
    strongreject_score,
)
from redharness.metrics.injection import (
    injection_success_rate,
    utility_baseline,
    utility_under_attack,
)

__all__ = [
    "asr",
    "asr_at_k",
    "frr",
    "injection_success_rate",
    "refusal_rate",
    "strongreject_score",
    "utility_baseline",
    "utility_under_attack",
]
