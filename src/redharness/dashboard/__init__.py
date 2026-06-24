"""Leaderboard dashboard: aggregate every run's leaderboard.json into a Streamlit app.

The dashboard scans a runs directory, combines every ``*/leaderboard.json`` into a
unified model tagged by attack surface (:func:`aggregate_runs`), and presents it as a
Streamlit web app (:mod:`redharness.dashboard.app`). Streamlit is an optional extra
(``.[dashboard]``); the aggregator and the app's data-shaping helpers import without it.
It is the read side of the leaderboard contract (plan §5/§8).
"""

from redharness.dashboard.aggregate import (
    DashboardData,
    DashboardRow,
    aggregate_runs,
    surface_for_metric,
)

__all__ = [
    "DashboardData",
    "DashboardRow",
    "aggregate_runs",
    "surface_for_metric",
]
