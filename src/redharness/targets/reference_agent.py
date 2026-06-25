"""A deterministic reference tool-calling agent for offline evaluation and CI.

``ReferenceAgent`` is a scripted, simulated stand-in for a real tool-using agent —
it is NOT a real model. It follows an explicit plan the agent-loop driver hands it
through the system message, so its behaviour is fully deterministic — no model, no
randomness, no clock. (The live ``OpenAICompatTarget`` also works in the loop if its
endpoint supports tool calls, but is never exercised in offline tests.)

Susceptibility is configurable so tests exercise BOTH injection outcomes:

  * ``robust``     — ignores injected instructions; ISR = 0, utility = 1.
  * ``vulnerable`` — when it observes the injection marker in the conversation,
    it fires the attacker's tool call before resuming its plan; ISR = 1.

The driver embeds the benign plan and (for a vulnerable agent to "discover") the
attacker action in a structured control block in the system message. A real agent
would instead reason over the natural-language task and tool results; this
reference agent short-circuits that to stay deterministic while still flowing
through the exact same loop, transcript, and judging path.
"""

from __future__ import annotations

import json
from typing import Any

from redharness.core.models import Message, Response
from redharness.core.registry import register_target
from redharness.core.target import Target

#: Marker delimiting the driver's machine-readable control block in the system msg.
CONTROL_PREFIX = "<<REDHARNESS_AGENT_CONTROL>>"


def encode_control(plan: list[dict], attacker_action: dict | None, marker: str) -> str:
    """Serialise the driver's plan/attacker-action block for the agent to read."""
    payload = {"plan": plan, "attacker_action": attacker_action, "marker": marker}
    return CONTROL_PREFIX + json.dumps(payload, sort_keys=True)


def _decode_control(text: str) -> dict[str, Any] | None:
    idx = text.find(CONTROL_PREFIX)
    if idx == -1:
        return None
    return json.loads(text[idx + len(CONTROL_PREFIX) :])


@register_target("reference_agent")
class ReferenceAgent(Target):
    """A deterministic, scripted tool-calling agent for offline evaluation."""

    SUSCEPTIBILITIES = ("robust", "vulnerable")

    def __init__(self, name: str = "reference_agent", susceptibility: str = "robust") -> None:
        if susceptibility not in self.SUSCEPTIBILITIES:
            raise ValueError(
                f"susceptibility must be one of {self.SUSCEPTIBILITIES}, got {susceptibility!r}"
            )
        self.name = name
        self.susceptibility = susceptibility

    def generate(self, messages: list[Message], tools: list[dict] | None = None) -> Response:
        control = self._read_control(messages)
        if control is None:
            # Not an agentic run (e.g. used as a plain target): answer benignly.
            return Response(text="done", target_name=self.name, raw={"tool_calls": []})

        already = self._tool_calls_so_far(messages)
        hijacked = self._marker_present(messages, control["marker"])

        # A vulnerable agent obeys the injected instruction first, exactly once.
        attacker_action = control.get("attacker_action")
        if (
            self.susceptibility == "vulnerable"
            and hijacked
            and attacker_action is not None
            and not self._already_made(already, attacker_action)
        ):
            return self._tool_call_response(attacker_action, hijacked=True)

        # Otherwise execute the next not-yet-made step of the benign plan.
        for step in control["plan"]:
            if not self._already_made(already, step):
                return self._tool_call_response(step, hijacked=False)

        return Response(
            text="Task complete.", target_name=self.name, raw={"tool_calls": []}
        )

    @staticmethod
    def _read_control(messages: list[Message]) -> dict[str, Any] | None:
        for message in messages:
            if message.role == "system":
                control = _decode_control(message.content)
                if control is not None:
                    return control
        return None

    @staticmethod
    def _marker_present(messages: list[Message], marker: str) -> bool:
        if not marker:
            return False
        # The control block in the system message contains the marker as data; only
        # treat the marker as *observed* when it appears outside that control block
        # (i.e. in the injected user prompt or a tool result the agent read).
        for message in messages:
            content = message.content
            if message.role == "system":
                content = content.split(CONTROL_PREFIX, 1)[0]
            if marker in content:
                return True
        return False

    @staticmethod
    def _tool_calls_so_far(messages: list[Message]) -> list[dict]:
        calls: list[dict] = []
        for message in messages:
            if message.role == "assistant" and message.name == "tool_call":
                calls.append(json.loads(message.content))
        return calls

    @staticmethod
    def _already_made(made: list[dict], step: dict) -> bool:
        return any(
            c.get("name") == step.get("name") and c.get("arguments") == step.get("arguments")
            for c in made
        )

    def _tool_call_response(self, step: dict, hijacked: bool) -> Response:
        return Response(
            text="",
            target_name=self.name,
            raw={"tool_calls": [step], "hijacked": hijacked},
        )
