"""Base class for prompt-injection attacks.

An injection attack does not run a single-turn jailbreak; it produces an
:class:`Injection` — the malicious instruction string plus where it is placed —
which the agent-loop driver weaves into a scenario run (plan §5 Phase 2). The
attacker goal is expressed as a benign sentinel by the scenario, so the attack
only needs to phrase the instruction and declare its placement.

Real attack corpora (AgentDojo's attack strings, InjecAgent's injected
instructions) plug in here: a corpus-backed attack would subclass this, load the
external strings behind a dependency extra (mirroring ``attacks/external``), and
emit one :class:`Injection` per corpus entry. We deliberately do NOT bundle those
strings — only benign templates that demonstrate the mechanism.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from redharness.core.scenario import Injection, Scenario


class InjectionAttack(ABC):
    """Produces an :class:`Injection` for a given scenario."""

    name: str = "injection"

    @abstractmethod
    def build_injection(self, scenario: Scenario) -> Injection | None:
        """Return the injection to weave into ``scenario``'s run, or ``None``.

        ``None`` means no attacker is present — the baseline-utility run in which
        the agent does its real job unperturbed (utility_baseline, plan §6).
        """
        raise NotImplementedError
