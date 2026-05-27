"""Stable interfaces and data models — the extensibility contract.

Five pluggable axes (Target, Attack, Dataset, Judge, Metric) for the jailbreak
surface, plus the Scenario / injection axes for the agentic prompt-injection
surface, all discoverable through a typed ``Registry``.
"""

from redharness.core.attack import Attack
from redharness.core.dataset import Dataset
from redharness.core.judge import Judge
from redharness.core.metric import Metric, MetricResult
from redharness.core.models import (
    Attempt,
    Behavior,
    Message,
    Response,
    Verdict,
)
from redharness.core.registry import (
    Registry,
    register_attack,
    register_dataset,
    register_judge,
    register_metric,
    register_target,
    registry,
)
from redharness.core.scenario import Scenario
from redharness.core.target import Target

__all__ = [
    "Attack",
    "Attempt",
    "Behavior",
    "Dataset",
    "Judge",
    "Message",
    "Metric",
    "MetricResult",
    "Registry",
    "Response",
    "Scenario",
    "Target",
    "Verdict",
    "register_attack",
    "register_dataset",
    "register_judge",
    "register_metric",
    "register_target",
    "registry",
]
