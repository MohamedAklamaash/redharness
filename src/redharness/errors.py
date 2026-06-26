"""Typed exception hierarchy for redharness.

Keeping every failure mode behind a named exception lets the CLI map errors to
clear messages and non-zero exit codes, and lets tests assert on precise types
rather than brittle string matching.
"""

from __future__ import annotations


class RedharnessError(Exception):
    """Base class for all redharness errors."""


class RegistryError(RedharnessError):
    """Raised when a plugin name cannot be resolved or is registered twice."""


class ConfigError(RedharnessError):
    """Raised when a run config is malformed or references unknown plugins."""


class TargetConfigError(RedharnessError):
    """Raised when a target is misconfigured (e.g. missing API credentials or
    a missing optional extra). These are non-retryable and surfaced at construction
    or before any retry is attempted."""


class TargetRuntimeError(RedharnessError):
    """Raised when a live target call fails transiently or at runtime.

    Covers exhausted retries (429/5xx), connection/read timeouts, non-auth 4xx
    (e.g. 400 validation), and unparseable response bodies. Distinct from
    :class:`TargetConfigError` so callers (e.g. the PAIR loop) can degrade to a
    best-effort attempt on runtime failures while still aborting on misconfig.
    """


class RunBudgetExceeded(RedharnessError):
    """Raised when a run exceeds its configured ``max_queries`` budget.

    The budget is enforced fail-closed: the run aborts cleanly with this typed
    error rather than silently overspending against a paid provider.
    """


class ExternalAttackUnavailable(RedharnessError):
    """Raised when an external-attack scaffold is invoked without its heavy extra.

    The GCG/garak/PyRIT adapters are registered seams whose heavy dependency is
    imported lazily inside :meth:`run`; a missing install (or the fact that the
    scaffold is unverified in CI) is surfaced as this typed error naming the extra,
    never a bare ``ImportError`` deep in a call stack.
    """


class DatasetError(RedharnessError):
    """Raised when a dataset cannot be loaded or fails hash verification."""


class DatasetHashMismatch(DatasetError):
    """Raised when a dataset file's sha256 does not match its manifest."""


class LeakageConfigError(RedharnessError):
    """Raised when a leakage behavior or probe is missing its ground-truth secret."""


class DashboardError(RedharnessError):
    """Raised when the dashboard cannot read its runs directory."""
