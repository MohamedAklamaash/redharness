"""A generic OpenAI-compatible ``/chat/completions`` adapter.

This is the bring-your-own-model path. It is hardened but stays out of the offline
deterministic slice: ``httpx`` is imported lazily (so installing redharness without
the ``openai`` extra still imports cleanly) and missing credentials raise a typed
:class:`TargetConfigError` at construction rather than failing deep in a request.

Configuration is per-instance so a target, a PAIR attacker and a grader can use
distinct endpoints/keys. Credentials come ONLY from the environment so secrets
never live in a YAML config:

    base_url      : passed in config, or falls back to ``REDHARNESS_OPENAI_BASE_URL``
    api_key_env   : NAME of the env var holding the bearer token
                    (default ``REDHARNESS_OPENAI_API_KEY``)

Endpoint: ``POST {base_url}/chat/completions``. Retry/backoff, timeout and typed
errors are shared via :class:`~redharness.targets._http.HttpTarget`.
"""

from __future__ import annotations

import json
import os
from typing import Any

from redharness.core.models import Message, Response, Usage
from redharness.core.registry import register_target
from redharness.errors import TargetConfigError
from redharness.targets._http import HttpTarget

BASE_URL_ENV = "REDHARNESS_OPENAI_BASE_URL"
API_KEY_ENV = "REDHARNESS_OPENAI_API_KEY"


@register_target("openai_compat")
class OpenAICompatTarget(HttpTarget):
    """Calls any OpenAI-compatible chat endpoint, hardened with retry/backoff."""

    extra = "openai"

    def __init__(
        self,
        model: str,
        name: str | None = None,
        base_url: str | None = None,
        api_key_env: str = API_KEY_ENV,
        temperature: float = 0.0,
        timeout: float = 60.0,
        max_retries: int = 2,
        transport: Any | None = None,
    ) -> None:
        resolved_base = base_url or os.environ.get(BASE_URL_ENV)
        if not resolved_base:
            raise TargetConfigError(
                f"OpenAICompatTarget requires a base_url (config) or {BASE_URL_ENV} (env)"
            )
        self.temperature = temperature
        super().__init__(
            model,
            name=name or f"openai_compat:{model}",
            base_url=resolved_base,
            api_key_env=api_key_env,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
        )

    def generate(self, messages: list[Message], tools: list[dict] | None = None) -> Response:
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if tools:
            body["tools"] = tools
        headers = {"Authorization": f"Bearer {self._api_key}"}
        data, attempts = self._request_json(
            f"{self.base_url}/chat/completions", body, headers
        )
        data["tool_calls"] = _extract_tool_calls(data)
        return Response(
            text=_extract_text(data),
            target_name=self.name,
            raw=data,
            http_calls=attempts,
            usage=_extract_usage(data),
        )


def _message(data: dict[str, Any]) -> dict[str, Any] | None:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    return message if isinstance(message, dict) else None


def _extract_text(data: dict[str, Any]) -> str:
    """Pull ``choices[0].message.content`` defensively; empty on anything missing."""
    message = _message(data)
    if message is None:
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _extract_tool_calls(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize OpenAI ``message.tool_calls`` to ``[{name, arguments, call_id}]``.

    The OpenAI function-call shape nests the name and a JSON *string* of arguments
    under ``tool_calls[].function``; this parses that string and flattens it into
    the normalized list the agent loop reads from ``raw['tool_calls']``.
    """
    message = _message(data)
    if message is None:
        return []
    raw_calls = message.get("tool_calls")
    if not isinstance(raw_calls, list):
        return []
    calls: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_calls):
        if not isinstance(raw, dict):
            continue
        function = raw.get("function")
        if not isinstance(function, dict):
            continue
        calls.append(
            {
                "name": function.get("name", ""),
                "arguments": _parse_arguments(function.get("arguments")),
                "call_id": raw.get("id") or f"call-{index}",
            }
        )
    return calls


def _parse_arguments(arguments: Any) -> dict[str, Any]:
    """Decode the JSON-string ``arguments`` to a dict; empty on anything odd."""
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            decoded = json.loads(arguments)
        except (ValueError, TypeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _extract_usage(data: dict[str, Any]) -> Usage | None:
    """Normalize OpenAI ``usage.prompt_tokens``/``completion_tokens`` to ``Usage``."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    return Usage(
        input_tokens=_as_int(usage.get("prompt_tokens")),
        output_tokens=_as_int(usage.get("completion_tokens")),
    )


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None
