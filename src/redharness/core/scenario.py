"""The Scenario axis: the injection / agentic surface (interface only this phase).

Jailbreak evaluation needs only Attack x Target x Judge. Prompt injection adds a
*sandboxed tool environment* into which an attacker payload is smuggled, with
success defined as an attacker-controlled tool call firing while the agent's
benign task is (or is not) still completed (plan §3, §5 Phase 2;
AgentDojo / InjecAgent). That environment is out of scope for the offline
jailbreak slice, so this is a documented contract with no concrete
implementation yet — see ``attacks/external`` for where multi-turn orchestration
plugs in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from redharness.core.target import Target


class Scenario(ABC):
    """A sandboxed tool environment plus an injected attacker payload.

    Phase 2 will implement AgentDojo/InjecAgent-style scenarios. The contract:
    ``setup`` builds the tool sandbox, ``run`` drives the target agent through
    the task with the payload present, and the runner inspects the returned
    trace to decide whether the attacker tool-goal fired.
    """

    name: str = "scenario"

    @abstractmethod
    def setup(self) -> dict[str, Any]:  # pragma: no cover - interface only
        """Construct and return the sandboxed tool environment."""
        raise NotImplementedError

    @abstractmethod
    def run(self, target: Target, env: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
        """Drive ``target`` through the task in ``env``; return the trace."""
        raise NotImplementedError
