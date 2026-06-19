"""Aggregate every run's ``leaderboard.json`` into one unified, surface-tagged model.

A leaderboard row carries the (dataset_version, judge, metric) provenance triple
plus its attack/target/dataset and a value (``None`` = N/A). Here we load every
``runs/*/leaderboard.json``, tag each row with the attack *surface* its metric
belongs to, and combine them. Untrusted input is handled defensively: a missing
runs dir yields an empty dashboard, and a malformed file is skipped with a recorded
warning rather than aborting the whole aggregation (the leaderboard accepts
community submissions — plan §8).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

# Single source of truth: metric name -> attack surface. Unknown metrics fall back
# to "other" so a new or mistyped metric never crashes the dashboard.
_METRIC_SURFACE: dict[str, str] = {
    # jailbreak
    "asr": "jailbreak",
    "asr_at_k": "jailbreak",
    "refusal_rate": "jailbreak",
    "strongreject_score": "jailbreak",
    "frr": "jailbreak",
    # injection
    "injection_success_rate": "injection",
    "utility_under_attack": "injection",
    "utility_baseline": "injection",
    # leakage
    "extraction_rate": "leakage",
    "canary_exposure_rate": "leakage",
    "pii_leak_rate": "leakage",
    "system_prompt_leak_rate": "leakage",
    "verbatim_overlap": "leakage",
}

# Stable display order for surface sections.
SURFACE_ORDER: tuple[str, ...] = ("jailbreak", "injection", "leakage", "other")

# Metrics rendered as 0-1 rate bars in the visualization. Restricted to metrics
# whose value is a fraction so the bars are meaningful.
_RATE_METRICS: frozenset[str] = frozenset(
    {
        "asr",
        "asr_at_k",
        "refusal_rate",
        "strongreject_score",
        "frr",
        "injection_success_rate",
        "utility_under_attack",
        "utility_baseline",
        "extraction_rate",
        "canary_exposure_rate",
        "pii_leak_rate",
        "system_prompt_leak_rate",
        "verbatim_overlap",
    }
)

_REQUIRED_FIELDS: tuple[str, ...] = (
    "run_id",
    "attack",
    "target",
    "dataset",
    "dataset_version",
    "judge",
    "metric",
)


def surface_for_metric(metric: str) -> str:
    """Map a metric name to its attack surface, defaulting unknowns to ``other``."""
    return _METRIC_SURFACE.get(metric, "other")


class DashboardRow(BaseModel):
    """One leaderboard cell, tagged with its attack surface."""

    run_id: str
    attack: str
    target: str
    dataset: str
    dataset_version: str
    judge: str
    metric: str
    value: float | None = None
    surface: str
    is_rate: bool = False


class DashboardData(BaseModel):
    """The combined, surface-tagged view of every aggregated run."""

    rows: list[DashboardRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def run_count(self) -> int:
        return len({row.run_id for row in self.rows})

    @property
    def target_count(self) -> int:
        return len({row.target for row in self.rows})

    @property
    def surface_count(self) -> int:
        return len({row.surface for row in self.rows})

    @property
    def cell_count(self) -> int:
        return len(self.rows)


def _coerce_value(raw: object) -> float | None:
    """Coerce a row value to ``float | None``; treat anything unparsable as N/A."""
    if raw is None:
        return None
    if isinstance(raw, bool):  # bool is an int subclass; reject it explicitly.
        return None
    if isinstance(raw, int | float):
        return float(raw)
    return None


def _row_from_raw(raw: dict) -> DashboardRow:
    """Build a :class:`DashboardRow` from one untrusted leaderboard entry."""
    metric = str(raw["metric"])
    return DashboardRow(
        run_id=str(raw["run_id"]),
        attack=str(raw["attack"]),
        target=str(raw["target"]),
        dataset=str(raw["dataset"]),
        dataset_version=str(raw["dataset_version"]),
        judge=str(raw["judge"]),
        metric=metric,
        value=_coerce_value(raw.get("value")),
        surface=surface_for_metric(metric),
        is_rate=metric in _RATE_METRICS,
    )


def _load_leaderboard(path: Path) -> tuple[list[DashboardRow], str | None]:
    """Load one leaderboard file; return (rows, warning). Never raises on bad data."""
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"{path}: unreadable leaderboard.json ({exc.__class__.__name__})"

    if not isinstance(payload, list):
        return [], f"{path}: expected a list of rows, got {type(payload).__name__}"

    rows: list[DashboardRow] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict) or any(field not in raw for field in _REQUIRED_FIELDS):
            return [], f"{path}: row {index} is missing required fields; skipped file"
        rows.append(_row_from_raw(raw))
    return rows, None


def _sort_key(row: DashboardRow) -> tuple:
    """Deterministic ordering: surface, then target/attack/dataset/metric/run."""
    return (
        SURFACE_ORDER.index(row.surface) if row.surface in SURFACE_ORDER else len(SURFACE_ORDER),
        row.target,
        row.attack,
        row.dataset,
        row.metric,
        row.run_id,
    )


def aggregate_runs(runs_dir: Path) -> DashboardData:
    """Scan ``runs_dir`` for every ``*/leaderboard.json`` and combine them.

    A missing/empty directory yields an empty :class:`DashboardData` (a friendly
    "no runs yet" state, not an error). Malformed files are skipped with a recorded
    warning so one bad submission cannot poison the whole dashboard.
    """
    runs_dir = Path(runs_dir)
    data = DashboardData()
    if not runs_dir.is_dir():
        return data

    for path in sorted(runs_dir.glob("*/leaderboard.json")):
        rows, warning = _load_leaderboard(path)
        if warning is not None:
            data.warnings.append(warning)
            continue
        data.rows.extend(rows)

    data.rows.sort(key=_sort_key)
    return data
