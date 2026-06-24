"""Streamlit leaderboard dashboard for redharness.

The read side of the leaderboard contract (plan §5/§8): it aggregates every
``runs/*/leaderboard.json`` via :func:`aggregate_runs`, groups the rows by attack
surface, and presents per-surface tables and rate bar charts with sidebar filters.

The data-shaping logic (``DashboardData`` -> rows / pandas frames, surface grouping,
N/A formatting) is pure and importable without launching a server, so it can be unit
tested directly. Streamlit and pandas are an *optional* extra: they are imported
lazily inside the UI/frame helpers, so this module imports cleanly in the core dev
environment (and the test suite) without them. Submitted leaderboards are untrusted —
every value is rendered as data through Streamlit widgets, never as HTML.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from redharness.dashboard.aggregate import (
    SURFACE_ORDER,
    DashboardData,
    DashboardRow,
    aggregate_runs,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

# Env var the CLI launcher uses to pass the runs directory into the Streamlit
# subprocess (Streamlit scripts cannot rely on argv before ``--``).
RUNS_DIR_ENV = "REDHARNESS_RUNS_DIR"
DEFAULT_RUNS_DIR = "runs"

NA_DISPLAY = "—"

# Column order for the per-surface tables.
TABLE_COLUMNS: tuple[str, ...] = (
    "target",
    "attack",
    "dataset",
    "judge",
    "metric",
    "value",
)

# Human-readable surface section titles.
SURFACE_TITLES: dict[str, str] = {
    "jailbreak": "Jailbreak",
    "injection": "Prompt injection",
    "leakage": "Data leakage",
    "other": "Other",
}


def runs_dir_default() -> str:
    """Initial runs directory: the env var if set, else the ``runs`` default."""
    return os.environ.get(RUNS_DIR_ENV, DEFAULT_RUNS_DIR)


def load_data(runs_dir: str | Path) -> DashboardData:
    """Aggregate every ``runs_dir/*/leaderboard.json`` into one model."""
    return aggregate_runs(Path(runs_dir))


def format_value(value: float | None) -> str:
    """Render a metric value as a string, with N/A shown as an em dash."""
    if value is None:
        return NA_DISPLAY
    return f"{value:.3f}"


def _row_record(row: DashboardRow) -> dict[str, Any]:
    """Flatten a row to a table record, formatting N/A for display."""
    return {
        "target": row.target,
        "attack": row.attack,
        "dataset": row.dataset,
        "judge": row.judge,
        "metric": row.metric,
        "value": format_value(row.value),
    }


def rows_for_surface(data: DashboardData, surface: str) -> list[DashboardRow]:
    """Return the rows belonging to ``surface`` (aggregator order preserved)."""
    return [row for row in data.rows if row.surface == surface]


def present_surfaces(data: DashboardData) -> list[str]:
    """Surfaces that have at least one row, in stable display order."""
    present = {row.surface for row in data.rows}
    return [surface for surface in SURFACE_ORDER if surface in present]


def build_frame(rows: list[DashboardRow]) -> pd.DataFrame:
    """Build a display DataFrame from rows (N/A formatted as em dashes).

    pandas is imported lazily so the core package and tests do not require it.
    """
    import pandas as pd

    records = [_row_record(row) for row in rows]
    return pd.DataFrame.from_records(records, columns=list(TABLE_COLUMNS))


def build_rate_chart_frame(rows: list[DashboardRow]) -> pd.DataFrame:
    """Build a target-by-metric matrix of 0-1 rate values for a bar chart.

    Only rate metrics with a numeric value contribute; N/A cells are dropped. The
    result is indexed by target with one column per rate metric, ready for
    ``st.bar_chart``. Returns an empty frame when no rate cells exist.
    """
    import pandas as pd

    records = [
        {"target": row.target, "metric": row.metric, "value": row.value}
        for row in rows
        if row.is_rate and row.value is not None
    ]
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame.from_records(records)
    return frame.pivot_table(
        index="target", columns="metric", values="value", aggfunc="mean"
    )


def filter_rows(
    rows: list[DashboardRow],
    *,
    surfaces: list[str] | None = None,
    targets: list[str] | None = None,
    metrics: list[str] | None = None,
    attack_query: str = "",
    search: str = "",
) -> list[DashboardRow]:
    """Apply the sidebar filters to a list of rows.

    An empty/None selection means "no filter" for that axis. ``attack_query`` and
    ``search`` are case-insensitive substring matches (search spans target, attack,
    dataset, judge, and metric).
    """
    attack_q = attack_query.strip().lower()
    search_q = search.strip().lower()

    def keep(row: DashboardRow) -> bool:
        if surfaces and row.surface not in surfaces:
            return False
        if targets and row.target not in targets:
            return False
        if metrics and row.metric not in metrics:
            return False
        if attack_q and attack_q not in row.attack.lower():
            return False
        if search_q:
            haystack = " ".join(
                (row.target, row.attack, row.dataset, row.judge, row.metric)
            ).lower()
            if search_q not in haystack:
                return False
        return True

    return [row for row in rows if keep(row)]


def _sorted_unique(values: list[str]) -> list[str]:
    return sorted(set(values))


def main() -> None:  # pragma: no cover - exercised only under a live server
    """Streamlit entry point. Imported lazily so the core env need not have it."""
    import streamlit as st

    st.set_page_config(page_title="redharness leaderboard", layout="wide")
    st.title("redharness leaderboard")
    st.caption(
        "Aggregated adversarial-evaluation results across jailbreak, prompt-injection, "
        "and data-leakage surfaces."
    )

    st.sidebar.header("Filters")
    runs_dir = st.sidebar.text_input("Runs directory", value=runs_dir_default())
    data = load_data(runs_dir)

    if not data.rows:
        st.info(
            f"No runs yet. Run an evaluation (e.g. `redharness run configs/smoke.yaml`) "
            f"then point this dashboard at the runs directory (`{runs_dir}`)."
        )
        for warning in data.warnings:
            st.warning(warning)
        return

    all_surfaces = present_surfaces(data)
    all_targets = _sorted_unique([row.target for row in data.rows])
    all_metrics = _sorted_unique([row.metric for row in data.rows])

    surface_sel = st.sidebar.multiselect(
        "Surfaces", options=all_surfaces, default=all_surfaces
    )
    target_sel = st.sidebar.multiselect("Targets", options=all_targets)
    metric_sel = st.sidebar.multiselect("Metrics", options=all_metrics)
    attack_query = st.sidebar.text_input("Attack/probe filter", value="")
    search = st.sidebar.text_input("Search", value="")

    rows = filter_rows(
        data.rows,
        surfaces=surface_sel,
        targets=target_sel,
        metrics=metric_sel,
        attack_query=attack_query,
        search=search,
    )

    filtered = DashboardData(rows=rows, warnings=data.warnings)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Runs", filtered.run_count)
    col2.metric("Targets", filtered.target_count)
    col3.metric("Surfaces", filtered.surface_count)
    col4.metric("Metric cells", filtered.cell_count)

    for warning in data.warnings:
        st.warning(warning)

    if not rows:
        st.info("No rows match the current filters.")
        return

    for surface in present_surfaces(filtered):
        surface_rows = rows_for_surface(filtered, surface)
        st.subheader(f"{SURFACE_TITLES.get(surface, surface.title())} "
                     f"({len(surface_rows)} cell(s))")
        st.dataframe(
            build_frame(surface_rows),
            use_container_width=True,
            hide_index=True,
        )
        chart = build_rate_chart_frame(surface_rows)
        if not chart.empty:
            st.bar_chart(chart)


if __name__ == "__main__":  # pragma: no cover
    main()
