"""GCG scaffold: Greedy Coordinate Gradient adversarial suffixes (Zou et al. 2023).

GCG (arXiv:2307.15043) optimises an adversarial suffix against a white-box model and
needs ``torch`` (plus model weights). That is far outside the dependency-free offline
core, so this is a registered seam only: :meth:`run` lazily probes ``torch`` and
raises a typed :class:`~redharness.errors.ExternalAttackUnavailable` naming the
``gcg`` extra. It is unverified in CI.
"""

from __future__ import annotations

from redharness.attacks.external.base import ScaffoldAttack
from redharness.core.registry import register_attack


@register_attack("gcg")
class GCGAttack(ScaffoldAttack):
    """Registered scaffold for the GCG white-box suffix attack (extra: ``gcg``)."""

    name = "gcg"
    extra = "gcg"
    import_name = "torch"
