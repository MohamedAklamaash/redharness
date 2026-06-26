"""Metric plugins. Importing this package registers the built-in metrics."""

from redharness.metrics.core import (
    asr,
    asr_at_k,
    frr,
    refusal_rate,
    strongreject_score,
)
from redharness.metrics.cost import cost, token_usage
from redharness.metrics.injection import (
    injection_success_rate,
    utility_baseline,
    utility_under_attack,
)
from redharness.metrics.leakage import (
    canary_exposure_rate,
    extraction_rate,
    pii_leak_rate,
    system_prompt_leak_rate,
    verbatim_overlap,
)

__all__ = [
    "asr",
    "asr_at_k",
    "canary_exposure_rate",
    "cost",
    "extraction_rate",
    "frr",
    "injection_success_rate",
    "pii_leak_rate",
    "refusal_rate",
    "strongreject_score",
    "system_prompt_leak_rate",
    "token_usage",
    "utility_baseline",
    "utility_under_attack",
    "verbatim_overlap",
]
