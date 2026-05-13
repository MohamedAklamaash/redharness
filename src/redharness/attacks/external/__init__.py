"""Adapter surface for external, network-heavy attack frameworks.

This package is the documented seam where community attacks plug in without
pulling their dependencies into the offline core. None of these are implemented
in the offline slice; they are listed here so the extension contract is explicit.

Planned adapters (plan §1, §5 Phase 1):
  * PAIR  — Chao et al. 2023, attacker-LLM iterative refinement (arXiv:2310.08419)
  * TAP   — Mehrotra et al. 2023, tree of attacks with pruning (arXiv:2312.02119)
  * AutoDAN — Liu et al. 2023, genetic stealthy prompts (arXiv:2310.04451)
  * garak — NVIDIA probe/detector framework (github.com/NVIDIA/garak)
  * PyRIT — Microsoft multi-turn / crescendo orchestration (github.com/Azure/PyRIT)

Each adapter subclasses :class:`ExternalAttack`, declares its extra dependency
group, and translates the framework's transcript into ``Attempt`` objects so the
rest of the harness (judges, metrics, report) is unchanged.
"""

from redharness.attacks.external.base import ExternalAttack

__all__ = ["ExternalAttack"]
