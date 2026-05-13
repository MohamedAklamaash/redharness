"""A generic OpenAI-compatible ``/chat/completions`` adapter.

This is the bring-your-own-model path. It is intentionally *not* exercised in the
offline slice: the HTTP client is imported lazily so installing ``redharness``
without the ``openai`` extra still imports cleanly, and missing credentials raise
a typed :class:`TargetConfigError` rather than failing deep inside a request.

Configuration comes from the environment so secrets never live in a YAML config:
    REDHARNESS_OPENAI_BASE_URL  e.g. https://api.openai.com/v1
    REDHARNESS_OPENAI_API_KEY   the bearer token
The model id is passed in the run config.
"""

from __future__ import annotations

import os

from redharness.core.models import Message, Response
from redharness.core.registry import register_target
from redharness.core.target import Target
from redharness.errors import TargetConfigError

BASE_URL_ENV = "REDHARNESS_OPENAI_BASE_URL"
API_KEY_ENV = "REDHARNESS_OPENAI_API_KEY"


@register_target("openai_compat")
class OpenAICompatTarget(Target):
    """Calls any OpenAI-compatible chat endpoint configured via env vars."""

    def __init__(
        self,
        model: str,
        name: str | None = None,
        temperature: float = 0.0,
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.name = name or f"openai_compat:{model}"
        self.temperature = temperature
        self.timeout = timeout
        self._base_url = os.environ.get(BASE_URL_ENV)
        self._api_key = os.environ.get(API_KEY_ENV)
        if not self._base_url or not self._api_key:
            raise TargetConfigError(
                f"OpenAICompatTarget requires {BASE_URL_ENV} and {API_KEY_ENV} to be set"
            )

    def generate(self, messages: list[Message], tools: list[dict] | None = None) -> Response:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - exercised only with extra installed
            raise TargetConfigError(
                "OpenAICompatTarget needs the 'openai' extra: pip install 'redharness[openai]'"
            ) from exc

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        response = httpx.post(
            f"{self._base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        return Response(text=text, target_name=self.name, raw=data)
