"""Leaderboard dashboard: aggregate every run's leaderboard.json into one page.

The dashboard scans a runs directory, combines every ``*/leaderboard.json`` into a
unified model tagged by attack surface, and renders one self-contained static HTML
file that opens offline. It is the read side of the leaderboard contract (plan §5/§8).
"""

from redharness.dashboard.aggregate import (
    DashboardData,
    aggregate_runs,
    surface_for_metric,
)
from redharness.dashboard.render import render_dashboard, write_dashboard

__all__ = [
    "DashboardData",
    "aggregate_runs",
    "render_dashboard",
    "surface_for_metric",
    "write_dashboard",
]
