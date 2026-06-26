"""An Anthropic Messages API adapter, hardened and offline-testable.

Like :mod:`redharness.targets.openai_compat`, ``httpx`` is imported lazily and the
key is read only from the environment, so the offline core imports without the
``anthropic`` extra and a missing key fails fast as :class:`TargetConfigError`.

Authoritative Messages API contract (https://docs.anthropic.com):
  * ``POST {base_url}/messages`` (default base_url ``https://api.anthropic.com/v1``)
  * headers ``x-api-key``, ``anthropic-version: 2023-06-01``, ``content-type``
  * body ``{model, max_tokens (required), system?, messages: [{role, content}]}``
  * ``role:"system"`` messages are hoisted out of ``messages`` into the top-level
    ``system`` string (the Messages API has no system role inside ``messages``).
  * ``temperature`` is omitted by default; it is only sent when explicitly set AND
    the model supports it (some models 400 on sampling params).
  * response ``content`` is a list of blocks; text is the concatenation of the
    ``text`` of ``type=="text"`` blocks. ``stop_reason == "refusal"`` (HTTP 200,
    possibly empty content) is handled as a blocked/empty response, never a crash.
"""

from __future__ import annotations

from typing import Any

from redharness.core.models import Message, Response, Usage
from redharness.core.registry import register_target
from redharness.errors import TargetRuntimeError
from redharness.targets._http import HttpTarget

API_KEY_ENV = "ANTHROPIC_API_KEY"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_MODEL = "claude-opus-4-8"

#: Current Anthropic model ids (bare strings, no date suffix).
MODEL_IDS: tuple[str, ...] = (
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-fable-5",
    "claude-opus-4-7",
    "claude-opus-4-6",
)

#: Models that return HTTP 400 if ``temperature``/``top_p``/``top_k`` is supplied.
SAMPLING_UNSUPPORTED: frozenset[str] = frozenset(
    {"claude-opus-4-8", "claude-opus-4-7", "claude-fable-5"}
)


@register_target("anthropic")
class AnthropicTarget(HttpTarget):
    """Calls the Anthropic Messages API, hardened with shared retry/backoff."""

    extra = "anthropic"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        name: str | None = None,
        base_url: str | None = None,
        api_key_env: str = API_KEY_ENV,
        max_tokens: int = 1024,
        temperature: float | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        transport: Any | None = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.temperature = temperature
        super().__init__(
            model,
            name=name or f"anthropic:{model}",
            base_url=base_url or DEFAULT_BASE_URL,
            api_key_env=api_key_env,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
        )

    def generate(self, messages: list[Message], tools: list[dict] | None = None) -> Response:
        body = self._build_body(messages)
        if tools:
            body["tools"] = [_to_anthropic_tool(tool) for tool in tools]
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        data, attempts = self._request_json(f"{self.base_url}/messages", body, headers)
        data["tool_calls"] = _extract_tool_calls(data)
        return Response(
            text=_extract_text(data),
            target_name=self.name,
            raw=data,
            http_calls=attempts,
            usage=_extract_usage(data),
        )

    def _build_body(self, messages: list[Message]) -> dict[str, Any]:
        system_parts = [m.content for m in messages if m.role == "system"]
        # The Messages API has no ``tool`` role inside ``messages`` (tool results are
        # user-role content blocks this text-only adapter does not construct). Rather
        # than silently drop such content — which could leave an empty array — refuse
        # explicitly so the caller knows the transcript is unsupported here.
        allowed = ("system", "user", "assistant")
        unsupported = sorted({m.role for m in messages if m.role not in allowed})
        if unsupported:
            raise TargetRuntimeError(
                f"{self.name}: the Anthropic Messages adapter supports only "
                f"system/user/assistant roles; unsupported role(s): {unsupported}"
            )
        turns = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        # After hoisting ``system`` out, a system-only transcript leaves ``messages``
        # empty; the Messages API 400s on that, so fail with a clear typed error
        # instead of sending an invalid request.
        if not turns:
            raise TargetRuntimeError(
                f"{self.name}: cannot send a request with no user/assistant messages "
                "(the Messages API rejects an empty 'messages' array)"
            )
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": turns,
        }
        if system_parts:
            body["system"] = "\n".join(system_parts)
        if self.temperature is not None and self.model not in SAMPLING_UNSUPPORTED:
            body["temperature"] = self.temperature
        return body


def _extract_text(data: dict[str, Any]) -> str:
    """Concatenate text blocks; empty for a refusal or any missing/odd shape."""
    blocks = data.get("content")
    if not isinstance(blocks, list):
        return ""
    parts = [
        block["text"]
        for block in blocks
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    return "".join(parts)


def _extract_tool_calls(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Anthropic ``tool_use`` blocks to ``[{name, arguments, call_id}]``.

    The Messages API returns tool calls as ``content[]`` blocks of
    ``type == "tool_use"`` carrying ``name`` and an ``input`` dict; this flattens
    them into the normalized list the agent loop reads from ``raw['tool_calls']``.
    """
    blocks = data.get("content")
    if not isinstance(blocks, list):
        return []
    calls: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        arguments = block.get("input")
        calls.append(
            {
                "name": block.get("name", ""),
                "arguments": arguments if isinstance(arguments, dict) else {},
                "call_id": block.get("id") or f"call-{index}",
            }
        )
    return calls


def _to_anthropic_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Translate an OpenAI ``function`` tool schema to the Anthropic tool shape.

    The agent loop emits the OpenAI ``{type: function, function: {...}}`` schema;
    Anthropic expects ``{name, description, input_schema}``. A tool already in the
    Anthropic shape (or any unrecognised shape) is passed through unchanged.
    """
    function = tool.get("function") if isinstance(tool, dict) else None
    if not isinstance(function, dict):
        return tool
    return {
        "name": function.get("name", ""),
        "description": function.get("description", ""),
        "input_schema": function.get("parameters", {"type": "object"}),
    }


def _extract_usage(data: dict[str, Any]) -> Usage | None:
    """Normalize Anthropic ``usage.input_tokens``/``output_tokens`` to ``Usage``."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    return Usage(
        input_tokens=_as_int(usage.get("input_tokens")),
        output_tokens=_as_int(usage.get("output_tokens")),
    )


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None
