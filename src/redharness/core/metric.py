"""The Metric axis: aggregates scored attempts into a single reported number.

Metrics are pure functions over ``(Behavior, Attempt, Verdict)`` triples. To make
them discoverable by name from YAML while keeping them functions, each is wrapped
in a thin :class:`Metric` that pairs the callable with its name.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from redharness.core.models import Attempt, Behavior, Verdict

ScoredAttempts = list[tuple[Behavior, Attempt, Verdict]]


class MetricResult(BaseModel):
    """The output of a metric: a headline value plus an auditable breakdown."""

    name: str
    value: float
    breakdown: dict[str, Any] = Field(default_factory=dict)


MetricFn = Callable[[ScoredAttempts], MetricResult]


class Metric:
    """Wraps a metric function so it is registrable and callable by name."""

    def __init__(self, name: str, fn: MetricFn) -> None:
        self.name = name
        self._fn = fn

    def compute(self, scored: ScoredAttempts) -> MetricResult:
        return self._fn(scored)
