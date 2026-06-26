"""garak scaffold: NVIDIA's LLM probe/detector framework (github.com/NVIDIA/garak).

garak runs its own probe/detector pipeline and pulls a large dependency tree, so this
is a registered seam only: :meth:`run` lazily probes the ``garak`` package and raises
a typed :class:`~redharness.errors.ExternalAttackUnavailable` naming the ``garak``
extra. A real implementation would translate garak's probe results into ``Attempt``
objects. It is unverified in CI.
"""

from __future__ import annotations

from redharness.attacks.external.base import ScaffoldAttack
from redharness.core.registry import register_attack


@register_attack("garak")
class GarakAttack(ScaffoldAttack):
    """Registered scaffold for the garak probe framework (extra: ``garak``)."""

    name = "garak"
    extra = "garak"
    import_name = "garak"
