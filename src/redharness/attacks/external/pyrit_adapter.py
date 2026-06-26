"""PyRIT scaffold: Microsoft's risk-identification orchestration (github.com/Azure/PyRIT).

PyRIT orchestrates multi-turn / crescendo attacks through its own engine and pulls a
large dependency tree, so this is a registered seam only: :meth:`run` lazily probes
the ``pyrit`` package and raises a typed
:class:`~redharness.errors.ExternalAttackUnavailable` naming the ``pyrit`` extra. A
real implementation would translate a PyRIT orchestrator run into ``Attempt``
objects. It is unverified in CI.
"""

from __future__ import annotations

from redharness.attacks.external.base import ScaffoldAttack
from redharness.core.registry import register_attack


@register_attack("pyrit")
class PyRITAttack(ScaffoldAttack):
    """Registered scaffold for the PyRIT orchestration framework (extra: ``pyrit``)."""

    name = "pyrit"
    extra = "pyrit"
    import_name = "pyrit"
