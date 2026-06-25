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

import os
from typing import Any

from redharness.core.models import Message, Response
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
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        # ``raw`` is the parsed body ONLY (it carries ``usage`` for cost), so no
        # request header or API key can ever leak into a transcript/cache/board.
        # ``http_calls`` (retry-inclusive call count) is a bare int the run budget
        # charges; it carries no secret data.
        data, attempts = self._request_json(
            f"{self.base_url}/chat/completions", body, headers
        )
        return Response(
            text=_extract_text(data), target_name=self.name, raw=data, http_calls=attempts
        )


def _extract_text(data: dict[str, Any]) -> str:
    """Pull ``choices[0].message.content`` defensively; empty on anything missing."""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""
