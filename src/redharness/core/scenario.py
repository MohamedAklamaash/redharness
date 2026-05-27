"""The Scenario axis: the prompt-injection / agentic surface.

Jailbreak evaluation needs only Attack x Target x Judge over a single turn. Prompt
injection adds a *sandboxed tool environment* plus a benign user task, into which
an attacker instruction is smuggled — directly (appended to the user's prompt) or
indirectly (planted in a tool's returned content). Success is defined the way
AgentDojo / InjecAgent define it (Debenedetti et al. 2024; Zhan et al. 2024):

  * ``attacker_succeeded`` — the agent was hijacked into the attacker's goal
    (e.g. it called a sensitive tool with an attacker-chosen argument), and
  * ``user_task_completed`` — the agent still finished the benign user task.

Both are checkable predicates over the recorded transcript, so the offline path
stays fully deterministic. The attacker goals shipped here are BENIGN sentinels
(e.g. an email to ``attacker@evil.example``) that demonstrate the mechanism with
no harmful content.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel, Field

from redharness.core.tools import ToolCall, ToolEnvironment


class InjectionPlacement(StrEnum):
    """Where an injected instruction is delivered to the agent.

    ``USER_PROMPT`` is the *direct* vector (appended to the user's turn);
    ``TOOL_OUTPUT`` is the *indirect* vector (planted in a named tool's result).
    """

    USER_PROMPT = "user_prompt"
    TOOL_OUTPUT = "tool_output"


class Injection(BaseModel):
    """A concrete injection produced by an injection attack.

    ``instruction`` is the malicious string, ``placement`` says how it reaches the
    agent, and ``target_tool`` names the tool whose output carries it for the
    indirect vector (``None`` for the direct vector). ``marker`` is the substring a
    susceptible agent keys off, kept separate from the human-readable instruction
    so detection stays robust to template wording.
    """

    instruction: str
    placement: InjectionPlacement
    target_tool: str | None = None
    marker: str = ""
    template: str = "default"

    model_config = {"frozen": True}


class AgentTrace(BaseModel):
    """The structured record of one agent run through a scenario.

    The runner serialises this into ``Attempt.metadata`` so judges and metrics read
    structured outcomes rather than re-parsing transcript strings. ``injected``
    distinguishes an attacked run from the no-injection baseline (utility_baseline).
    """

    steps: list[dict] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    final_answer: str = ""
    injected: bool = False
    max_steps_hit: bool = False


class Scenario(ABC):
    """A sandboxed tool environment plus a benign user task and an attacker goal.

    Concrete scenarios build a fresh :class:`ToolEnvironment` per run (so state
    never leaks between attempts), state the benign ``user_task``, and expose two
    predicates over the recorded tool calls. ``attacker_goal`` is a human-readable
    description of the benign sentinel the attack tries to trigger; the predicates
    are the ground truth used by the judge.
    """

    name: str = "scenario"
    suite: str = "scenario"

    #: Human-readable benign user goal — also used as the agent's first user turn.
    user_task: str = ""
    #: Human-readable description of the (benign sentinel) attacker goal.
    attacker_goal: str = ""

    @abstractmethod
    def build_env(self) -> ToolEnvironment:
        """Construct a fresh sandboxed tool environment for one run."""
        raise NotImplementedError

    @abstractmethod
    def attacker_succeeded(self, calls: list[ToolCall]) -> bool:
        """True if the recorded tool calls achieved the attacker's goal."""
        raise NotImplementedError

    @abstractmethod
    def user_task_completed(self, calls: list[ToolCall]) -> bool:
        """True if the recorded tool calls completed the benign user task."""
        raise NotImplementedError

    @abstractmethod
    def control_block(self) -> tuple[list[dict], dict]:
        """The agent loop's offline plan for this scenario.

        Returns ``(user_plan, attacker_action)`` as plain serialisable dicts: the
        benign sequence of tool calls that completes the user task, and the single
        tool call the injection tries to make the agent fire. The agent-loop driver
        encodes these into the offline target's control block — declaring them here
        makes that an explicit part of the interface rather than a duck-typed
        ``scenario.spec`` reach-in.
        """
        raise NotImplementedError
