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

from redharness.core.models import Message, Response
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
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        # ``raw`` is the parsed body ONLY (carries ``usage``); the key never lands.
        # ``http_calls`` (retry-inclusive call count) is a bare int the run budget
        # charges; it carries no secret data.
        data, attempts = self._request_json(f"{self.base_url}/messages", body, headers)
        return Response(
            text=_extract_text(data), target_name=self.name, raw=data, http_calls=attempts
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
