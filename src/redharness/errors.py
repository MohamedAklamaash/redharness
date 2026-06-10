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
    """Raised when a target is misconfigured (e.g. missing API credentials)."""


class DatasetError(RedharnessError):
    """Raised when a dataset cannot be loaded or fails hash verification."""


class DatasetHashMismatch(DatasetError):
    """Raised when a dataset file's sha256 does not match its manifest."""


class LeakageConfigError(RedharnessError):
    """Raised when a leakage behavior or probe is missing its ground-truth secret."""
