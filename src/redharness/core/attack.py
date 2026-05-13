"""The Attack axis: turns a behavior into one or more attempts against a target."""

from __future__ import annotations

from abc import ABC, abstractmethod

from redharness.core.models import Attempt, Behavior
from redharness.core.target import Target


class Attack(ABC):
    """Generates probes for a behavior and runs them against a target.

    A static attack replays the behavior prompt once; a dynamic attack may issue
    many queries (counted in ``Attempt.query_count``) and produce several
    attempts. Attacks must be deterministic given a fixed seed so golden tests
    stay stable.
    """

    name: str = "attack"

    @abstractmethod
    def run(self, behavior: Behavior, target: Target) -> list[Attempt]:
        """Return the attempts produced for ``behavior`` against ``target``."""
        raise NotImplementedError
