"""Run-config schema and loading.

A run config is a declarative experiment spec: which attacks x targets x datasets
x judges x metrics to evaluate. It is validated with pydantic so malformed YAML
fails with a clear, typed :class:`ConfigError` before any model is queried.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from redharness.errors import ConfigError

# run_name becomes a directory under runs/, so restrict it to a safe slug: no
# path separators, no ``..``, no leading separators — anything that could escape
# the runs dir and overwrite arbitrary files via path traversal.
_RUN_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class PluginSpec(BaseModel):
    """A reference to a registered plugin plus its constructor kwargs."""

    name: str
    params: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class RunConfig(BaseModel):
    """A complete, validated run specification.

    A run is in one of two modes, determined by which axes are populated:

      * **jailbreak** — ``attacks`` x ``datasets`` (the Phase 1 matrix), or
      * **injection** — ``injections`` x ``scenarios`` (the Phase 2 agentic surface).

    The Phase 3 data-leakage surface is single-turn (probe -> response -> detect
    leak), structurally identical to the jailbreak matrix, so it reuses the
    **jailbreak** mode with leakage attacks, the ``leakage_demo`` dataset, the
    ``leak_detector`` judge, and the leakage metrics — no separate mode is needed.

    ``targets``, ``judges`` and ``metrics`` are shared by all. Exactly one mode
    must be configured, so a config is never ambiguous about what it runs.
    """

    run_name: str = "redharness-run"
    seed: int = 0
    max_steps: int = Field(default=6, ge=1, le=64)
    # Hard run-level query budget: the maximum number of REAL outbound provider
    # calls — counting transient retries (429/5xx/timeout) and every provider an
    # attack uses (e.g. PAIR's attacker + target + in-loop judge) — for the whole
    # run. Enforced fail-closed at the innermost call site: the run aborts with a
    # typed RunBudgetExceeded the instant the ceiling is crossed (bounded overshoot
    # is only the in-flight retries of one call), so a live eval can never overspend
    # against a paid provider. Cache hits do not count. ``None`` means unbounded
    # (the offline default); when set it is pydantic-bounded.
    max_queries: int | None = Field(default=None, ge=1, le=10_000_000)
    # Opt-in bounded concurrency for scale: independent behaviors/scenarios within a
    # cell are executed across this many worker threads. The default (1) keeps the
    # runner sequential and byte-identical to the deterministic offline path; results
    # are always assembled in deterministic order regardless of completion order.
    concurrency: int = Field(default=1, ge=1, le=64)
    # Multi-seed statistical rigor: repeat the whole matrix under seeds
    # ``seed .. seed+trials-1`` and aggregate each metric to its mean + a bootstrap CI
    # across trials. The default (1) is a single run, byte-identical to today. For
    # deterministic reference targets every trial is identical (CI width 0); the value
    # is realised against stochastic live targets.
    trials: int = Field(default=1, ge=1, le=100)
    targets: list[PluginSpec] = Field(min_length=1)
    judges: list[PluginSpec] = Field(min_length=1)
    metrics: list[str] = Field(min_length=1)
    attacks: list[PluginSpec] = Field(default_factory=list)
    datasets: list[PluginSpec] = Field(default_factory=list)
    injections: list[PluginSpec] = Field(default_factory=list)
    scenarios: list[PluginSpec] = Field(default_factory=list)

    model_config = {"extra": "forbid"}

    @property
    def mode(self) -> str:
        return "injection" if self.scenarios else "jailbreak"

    @field_validator("run_name")
    @classmethod
    def _validate_run_name(cls, value: str) -> str:
        if not _RUN_NAME_RE.fullmatch(value) or value in {".", ".."}:
            raise ValueError(
                f"run_name {value!r} is invalid: must match {_RUN_NAME_RE.pattern} "
                "(no path separators, no '..', 1-128 chars)"
            )
        return value

    @model_validator(mode="after")
    def _validate_mode(self) -> RunConfig:
        jailbreak = bool(self.attacks or self.datasets)
        injection = bool(self.injections or self.scenarios)
        if jailbreak and injection:
            raise ValueError(
                "config mixes modes: provide either (attacks + datasets) or "
                "(injections + scenarios), not both"
            )
        if injection:
            if not self.injections or not self.scenarios:
                raise ValueError(
                    "injection mode requires both 'injections' and 'scenarios'"
                )
        elif not self.attacks or not self.datasets:
            raise ValueError(
                "jailbreak mode requires both 'attacks' and 'datasets' "
                "(or configure 'injections' + 'scenarios' for the injection surface)"
            )
        return self


def _coerce_specs(raw: Any, axis: str) -> list[dict]:
    """Allow either ['name', ...] shorthand or [{name, params}, ...] longhand."""
    if not isinstance(raw, list):
        raise ConfigError(f"config field {axis!r} must be a list")
    specs: list[dict] = []
    for item in raw:
        if isinstance(item, str):
            specs.append({"name": item})
        elif isinstance(item, dict):
            specs.append(item)
        else:
            kind = type(item).__name__
            raise ConfigError(f"{axis} entry must be a string or mapping, got {kind}")
    return specs


def load_config(path: str | Path) -> RunConfig:
    """Load and validate a YAML run config from ``path``."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"config is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")

    for axis in ("targets", "attacks", "datasets", "judges", "injections", "scenarios"):
        if axis in raw:
            raw[axis] = _coerce_specs(raw[axis], axis)

    try:
        return RunConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid run config: {exc}") from exc
