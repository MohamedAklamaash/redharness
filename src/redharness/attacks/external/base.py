"""ABC for external attack-framework adapters (no heavy deps in the core)."""

from __future__ import annotations

from abc import abstractmethod

from redharness.core.attack import Attack
from redharness.core.models import Attempt, Behavior
from redharness.core.target import Target


class ExternalAttack(Attack):
    """Wraps a third-party attack framework behind the ``Attack`` interface.

    Concrete adapters (PAIR/TAP/AutoDAN/garak/PyRIT) import their framework
    lazily inside :meth:`run`, declare the extra dependency group needed to use
    them, and convert the framework's run into ``Attempt`` objects. They are not
    part of the offline slice.
    """

    #: pip extra that must be installed for this adapter, e.g. ``"pair"``.
    extra: str = ""

    @abstractmethod
    def run(self, behavior: Behavior, target: Target) -> list[Attempt]:  # pragma: no cover
        raise NotImplementedError
