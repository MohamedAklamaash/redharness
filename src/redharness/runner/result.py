"""Structured run results.

Each (attack x target x dataset x judge) combination is one :class:`CellResult`
carrying its metric values; every metric value records the
(dataset_version, judge, metric) triple so a number is never ambiguous (plan §6).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from redharness.core.metric import MetricResult


class CellResult(BaseModel):
    """Metrics for one attack x target x dataset x judge combination."""

    attack: str
    target: str
    dataset: str
    dataset_version: str
    judge: str
    metrics: dict[str, MetricResult] = Field(default_factory=dict)


class RunResult(BaseModel):
    """The full result of a run: every cell plus run-level metadata."""

    run_id: str
    run_name: str
    seed: int
    cells: list[CellResult] = Field(default_factory=list)
    transcript_path: str
