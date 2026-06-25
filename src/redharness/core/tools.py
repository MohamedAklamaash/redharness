"""Simulated tool model and a deterministic tool environment for the injection surface.

The injection / agentic surface (plan §3, §5 Phase 2) needs a sandbox: a set of
tools an agent may call and an environment that "executes" them. Every tool here
is simulated with benign semantics — no network, no real side effects, no wall
clock — so the offline path is fully deterministic (AgentDojo / InjecAgent model
the same way; Debenedetti et al. 2024, Zhan et al. 2024).

A tool call's *result content* is the indirect-injection vector: a scenario can
seed a document or email body with an attacker instruction, and the agent reads
it back through an ordinary tool result.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

ToolFn = Callable[["ToolEnvironment", dict[str, Any]], str]


class Tool(BaseModel):
    """A callable tool exposed to the agent.

    ``parameters`` is a JSON-schema-ish description of the arguments, matching the
    shape an OpenAI-compatible ``tools=`` payload expects, so the same model drives
    both the reference agent and a real tool-calling endpoint.
    """

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}

    def to_schema(self) -> dict[str, Any]:
        """Render the OpenAI ``function`` tool schema for ``generate(tools=...)``."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": sorted(self.parameters),
                },
            },
        }


class ToolCall(BaseModel):
    """A tool invocation proposed by the agent."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str = "call-0"

    model_config = {"frozen": True}


class ToolResult(BaseModel):
    """The outcome of executing a :class:`ToolCall` in the environment."""

    call_id: str
    name: str
    content: str = ""
    error: str | None = None

    model_config = {"frozen": True}

    @property
    def ok(self) -> bool:
        return self.error is None


class ToolEnvironment:
    """A deterministic sandbox that executes simulated tool calls.

    The environment owns a mutable ``state`` dict (e.g. a simulated inbox or
    document store) and a registry of tool implementations. Executing a call
    mutates only this in-memory state — there are no real side effects. Unknown
    tools and bad arguments return a :class:`ToolResult` carrying ``error`` rather
    than raising, so the agent loop can surface the failure to the model and keep
    going instead of crashing (plan §5 Phase 2: handle malformed calls gracefully).
    """

    def __init__(
        self,
        tools: list[Tool],
        handlers: dict[str, ToolFn],
        state: dict[str, Any] | None = None,
    ) -> None:
        self._tools = {t.name: t for t in tools}
        self._handlers = dict(handlers)
        missing = set(self._tools) - set(self._handlers)
        if missing:
            raise ValueError(f"tools without handlers: {sorted(missing)}")
        self.state: dict[str, Any] = dict(state or {})
        self.calls: list[ToolCall] = []

    def schemas(self) -> list[dict[str, Any]]:
        return [t.to_schema() for t in self._tools.values()]

    def execute(self, call: ToolCall) -> ToolResult:
        """Run ``call`` against the sandbox, recording it on ``calls``."""
        self.calls.append(call)
        tool = self._tools.get(call.name)
        if tool is None:
            known = ", ".join(sorted(self._tools)) or "(none)"
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                error=f"unknown tool {call.name!r}; available: {known}",
            )
        missing = [p for p in tool.parameters if p not in call.arguments]
        if missing:
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                error=f"missing required argument(s): {', '.join(sorted(missing))}",
            )
        content = self._handlers[call.name](self, call.arguments)
        return ToolResult(call_id=call.call_id, name=call.name, content=content)
