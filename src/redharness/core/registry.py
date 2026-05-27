"""A small typed plugin registry.

One ``Registry`` instance per axis keeps name collisions scoped (a target and an
attack may both be called ``"static"`` without clashing) while staying trivial to
reason about. Plugins register via decorators at import time and are resolved by
the string names that appear in YAML run configs.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from redharness.errors import RegistryError

T = TypeVar("T")


class Registry(Generic[T]):
    """Maps plugin names to classes for a single axis."""

    def __init__(self, axis: str) -> None:
        self.axis = axis
        self._entries: dict[str, type[T]] = {}

    def register(self, name: str) -> Callable[[type[T]], type[T]]:
        """Decorator that registers ``cls`` under ``name`` for this axis."""

        def decorator(cls: type[T]) -> type[T]:
            existing = self._entries.get(name)
            if existing is not None and existing is not cls:
                raise RegistryError(
                    f"{self.axis} plugin {name!r} is already registered to "
                    f"{existing.__name__}; cannot rebind to {cls.__name__}"
                )
            self._entries[name] = cls
            return cls

        return decorator

    def get(self, name: str) -> type[T]:
        try:
            return self._entries[name]
        except KeyError:
            known = ", ".join(sorted(self._entries)) or "(none registered)"
            raise RegistryError(
                f"unknown {self.axis} plugin {name!r}. Available: {known}"
            ) from None

    def names(self) -> list[str]:
        return sorted(self._entries)


class _Registries:
    """Container holding one registry per axis, exposed as a singleton."""

    def __init__(self) -> None:
        self.targets: Registry = Registry("target")
        self.attacks: Registry = Registry("attack")
        self.datasets: Registry = Registry("dataset")
        self.judges: Registry = Registry("judge")
        self.metrics: Registry = Registry("metric")
        # The injection/agentic surface (Phase 2): injection attacks and scenario
        # suites are their own axes, kept separate so a jailbreak ``attack`` and an
        # ``injection`` of the same name never clash.
        self.injections: Registry = Registry("injection")
        self.scenarios: Registry = Registry("scenario")

    def by_axis(self) -> dict[str, Registry]:
        return {
            "targets": self.targets,
            "attacks": self.attacks,
            "datasets": self.datasets,
            "judges": self.judges,
            "metrics": self.metrics,
            "injections": self.injections,
            "scenarios": self.scenarios,
        }


registry = _Registries()

register_target = registry.targets.register
register_attack = registry.attacks.register
register_dataset = registry.datasets.register
register_judge = registry.judges.register
register_metric = registry.metrics.register
register_injection = registry.injections.register
register_scenario = registry.scenarios.register
