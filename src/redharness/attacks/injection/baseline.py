"""The no-injection control: run the agent on its real task, no attacker.

This is the baseline against which utility-under-attack is measured (AgentDojo,
Debenedetti et al. 2024): if the agent cannot finish the benign task even with no
attacker present, a drop under attack is not attributable to the injection.
"""

from __future__ import annotations

from redharness.attacks.injection.base import InjectionAttack
from redharness.core.registry import register_injection
from redharness.core.scenario import Injection, Scenario


@register_injection("no_injection")
class NoInjectionAttack(InjectionAttack):
    """Produces no injection — the benign baseline run."""

    name = "no_injection"

    def build_injection(self, scenario: Scenario) -> Injection | None:
        return None
