"""Prompt-injection attacks. Importing this package registers them.

A no-injection ``NoInjectionAttack`` is included so the baseline-utility run (the
agent doing its job with no attacker present) flows through the same code path.
"""

from redharness.attacks.injection.attacks import (
    DirectInjectionAttack,
    IndirectInjectionAttack,
)
from redharness.attacks.injection.baseline import NoInjectionAttack

__all__ = ["DirectInjectionAttack", "IndirectInjectionAttack", "NoInjectionAttack"]
