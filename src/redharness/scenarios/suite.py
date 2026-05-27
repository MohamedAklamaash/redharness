"""Data-driven scenarios built from a hash-pinned suite spec.

A suite is a JSON file (under ``scenarios/data``) listing scenarios; each names a
toolkit, the benign user task, the seed state (documents / files the agent reads),
and two declarative checks — one for the benign user task and one for the attacker
goal. Keeping scenarios as data means new ones are added without code, while the
hash manifest gives the same fetch-and-verify guarantee as the demo dataset
(plan §7). Tool semantics stay in :mod:`redharness.scenarios.toolkits`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from redharness.core.scenario import Scenario
from redharness.core.tools import ToolCall, ToolEnvironment
from redharness.scenarios.toolkits import TOOLKIT_BUILDERS


class ToolCallCheck(BaseModel):
    """A declarative predicate: did a call to ``tool`` with matching args occur?

    ``args_contain`` matches when, for each key, the recorded argument *contains*
    the expected substring (case-insensitive) — robust to the agent padding a body
    with extra text while still firing the sensitive argument the check cares about.
    """

    tool: str
    args_contain: dict[str, str] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    def matches(self, call: ToolCall) -> bool:
        if call.name != self.tool:
            return False
        for key, expected in self.args_contain.items():
            actual = call.arguments.get(key)
            if not isinstance(actual, str) or expected.lower() not in actual.lower():
                return False
        return True

    def satisfied_by(self, calls: list[ToolCall]) -> bool:
        return any(self.matches(c) for c in calls)


class PlannedCall(BaseModel):
    """A tool call the agent intends to make (deterministic offline plan)."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class ScenarioSpec(BaseModel):
    """The on-disk definition of one injection scenario.

    ``user_plan`` is the benign sequence of tool calls that completes the user
    task; ``attacker_action`` is the single tool call the injection tries to make
    the agent fire. The offline :class:`MockAgentTarget` follows these
    deterministically; a real agent would instead derive them from ``user_task``
    and the tool results. ``user_check`` / ``attacker_check`` are the ground-truth
    predicates the judge uses — kept independent of the plan so a partially
    hijacked run is scored on what actually happened, not what was planned.
    """

    id: str
    suite: str
    toolkit: str
    user_task: str
    attacker_goal: str
    state: dict[str, Any] = Field(default_factory=dict)
    user_plan: list[PlannedCall] = Field(default_factory=list)
    attacker_action: PlannedCall
    user_check: ToolCallCheck
    attacker_check: ToolCallCheck
    injection_tool: str | None = None

    model_config = {"extra": "forbid"}


class SuiteScenario(Scenario):
    """A :class:`Scenario` materialised from a :class:`ScenarioSpec`."""

    def __init__(self, spec: ScenarioSpec) -> None:
        if spec.toolkit not in TOOLKIT_BUILDERS:
            known = ", ".join(sorted(TOOLKIT_BUILDERS))
            raise ValueError(f"unknown toolkit {spec.toolkit!r}; available: {known}")
        self.spec = spec
        self.name = spec.id
        self.suite = spec.suite
        self.user_task = spec.user_task
        self.attacker_goal = spec.attacker_goal

    def build_env(self) -> ToolEnvironment:
        tools, handlers = TOOLKIT_BUILDERS[self.spec.toolkit]()
        return ToolEnvironment(tools, handlers, state=self.spec.state)

    def attacker_succeeded(self, calls: list[ToolCall]) -> bool:
        return self.spec.attacker_check.satisfied_by(calls)

    def user_task_completed(self, calls: list[ToolCall]) -> bool:
        return self.spec.user_check.satisfied_by(calls)

    def control_block(self) -> tuple[list[dict], dict]:
        plan = [pc.model_dump() for pc in self.spec.user_plan]
        return plan, self.spec.attacker_action.model_dump()
