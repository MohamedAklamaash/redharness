"""Adapter surface for external, network-heavy attack frameworks.

This package is the documented seam where community attacks plug in without
pulling their dependencies into the offline core. None of these are implemented
in the offline slice; they are listed here so the extension contract is explicit.

Implemented (pure-Python orchestration over injected providers, offline-testable):
  * PAIR      — Chao et al. 2023, attacker-LLM iterative refinement (arXiv:2310.08419)
  * TAP       — Mehrotra et al. 2023, tree of attacks with pruning (arXiv:2312.02119)
  * Crescendo — Russinovich et al. 2024, multi-turn escalation (arXiv:2404.01833)

Scaffolds (registered seams, heavy dep imported lazily, unverified in CI):
  * GCG   — Zou et al. 2023, white-box suffix optimisation (extra: ``gcg`` → torch)
  * garak — NVIDIA probe/detector framework (extra: ``garak``)
  * PyRIT — Microsoft multi-turn / crescendo orchestration (extra: ``pyrit``)

Each adapter subclasses :class:`ExternalAttack`, declares its extra dependency
group, and translates the framework's transcript into ``Attempt`` objects so the
rest of the harness (judges, metrics, report) is unchanged.
"""

from redharness.attacks.external.base import ExternalAttack, ScaffoldAttack
from redharness.attacks.external.crescendo import CrescendoAttack
from redharness.attacks.external.garak_adapter import GarakAttack
from redharness.attacks.external.gcg import GCGAttack
from redharness.attacks.external.pair import PairAttack
from redharness.attacks.external.pyrit_adapter import PyRITAttack
from redharness.attacks.external.tap import TapAttack

__all__ = [
    "CrescendoAttack",
    "ExternalAttack",
    "GCGAttack",
    "GarakAttack",
    "PairAttack",
    "PyRITAttack",
    "ScaffoldAttack",
    "TapAttack",
]
