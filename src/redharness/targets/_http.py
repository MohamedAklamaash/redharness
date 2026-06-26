"""Shared, lazily-imported HTTP transport and retry/backoff for live adapters.

Both live adapters (:class:`~redharness.targets.openai_compat.OpenAICompatTarget`
and :class:`~redharness.targets.anthropic.AnthropicTarget`) talk to their provider
through this module so "hardened" is implemented and unit-tested *once*:

  * ``httpx`` is imported lazily, so importing redharness never requires the
    httpx-based extras (the offline core stays installable without them).
  * The client is per-instance and accepts an injected ``transport``, so an
    offline test can drive a real request/response cycle through
    ``httpx.MockTransport`` with no network, and a target, a PAIR attacker and a
    grader can each use distinct endpoints/keys.
  * Retry policy lives in one place: bounded, jittered exponential backoff on
    429 / 5xx / connection-or-read-timeout *only* — never on 4xx auth/validation.
    Every outbound HTTP call (including retries) is counted and returned so it can
    fold into the attempt's ``query_count``/cost.

Credentials come only from the environment (never YAML), and ``Response.raw`` is
populated *only* from the parsed JSON body — request headers and the API key are
never recorded, so a secret can never leak into a transcript, cache, or leaderboard.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from redharness.core.models import Message, Response
from redharness.core.target import Target
from redharness.errors import TargetConfigError, TargetRuntimeError

#: HTTP statuses we treat as transient and retry (auth/validation 4xx never retry).
RETRY_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504, 529})

_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_CAP_SECONDS = 8.0

#: Loopback hosts where cleartext ``http://`` is permitted (local self-hosted/vLLM).
_LOOPBACK_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})


def _require_secure_base_url(base_url: str) -> None:
    """Reject a non-``https`` ``base_url`` so the API key is never sent in cleartext.

    The only cleartext exception is loopback (``http://localhost`` / ``127.0.0.1`` /
    ``[::1]``), for local self-hosted or vLLM endpoints where the key never leaves
    the host. Any other ``http://`` (or scheme-less) URL raises
    :class:`TargetConfigError`.
    """
    parts = urlsplit(base_url)
    scheme = parts.scheme.lower()
    if scheme == "https":
        return
    host = (parts.hostname or "").lower()
    if scheme == "http" and host in _LOOPBACK_HOSTS:
        return
    raise TargetConfigError(
        f"base_url {base_url!r} must use https (the API key is sent in the request "
        "headers and would travel in cleartext otherwise); plain http:// is allowed "
        "only for loopback (localhost/127.0.0.1/[::1]) local endpoints"
    )


def load_httpx(extra: str):
    """Import ``httpx`` lazily, mapping a missing install to a typed error."""
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - depends on install profile
        raise TargetConfigError(
            f"this target requires the {extra!r} extra (httpx-based): "
            f"install it with `pip install 'redharness[{extra}]'`"
        ) from exc
    return httpx


def _backoff_seconds(retry_index: int, rng: random.Random) -> float:
    """Jittered exponential backoff: full-jitter over [0, min(cap, base*2**i)]."""
    ceiling = min(_BACKOFF_CAP_SECONDS, _BACKOFF_BASE_SECONDS * (2**retry_index))
    return rng.uniform(0.0, ceiling)


def request_with_retry(
    send: Callable[[], Any],
    *,
    httpx,
    max_retries: int,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> tuple[Any, int]:
    """Call ``send`` with bounded jittered backoff on transient failures.

    Returns ``(response, attempts)`` where ``attempts`` counts *every* outbound
    HTTP call made (initial + retries) so the caller can fold it into
    ``query_count``. Retries on 429/5xx and connection/read timeouts only; a 4xx
    other than 429 is returned immediately for the caller to map to a typed error.
    Exhausted timeouts raise :class:`TargetRuntimeError`.
    """
    rng = rng or random.Random(0)
    attempts = 0
    for retry_index in range(max_retries + 1):
        attempts += 1
        try:
            response = send()
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            if retry_index < max_retries:
                sleep(_backoff_seconds(retry_index, rng))
                continue
            raise TargetRuntimeError(
                f"request failed after {attempts} attempt(s): {type(exc).__name__}: {exc}"
            ) from exc
        if response.status_code in RETRY_STATUSES and retry_index < max_retries:
            sleep(_backoff_seconds(retry_index, rng))
            continue
        return response, attempts
    # Unreachable: the loop always returns or raises, but keep mypy/readers happy.
    raise TargetRuntimeError("request exhausted retries")  # pragma: no cover


class HttpTarget(Target):
    """Shared hardening for httpx-based live adapters.

    Subclasses set :attr:`extra` and implement :meth:`generate` using
    :meth:`_request_json`, passing the per-instance ``base_url``/``api_key_env``
    to ``super().__init__``. Credentials are read from the environment at
    construction so a missing key fails fast as :class:`TargetConfigError`.
    """

    #: pip extra that must be installed to use the adapter, e.g. ``"anthropic"``.
    extra: str = ""

    def __init__(
        self,
        model: str,
        *,
        name: str,
        base_url: str,
        api_key_env: str,
        timeout: float = 60.0,
        max_retries: int = 2,
        transport: Any | None = None,
    ) -> None:
        self.model = model
        self.name = name
        _require_secure_base_url(base_url)
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise TargetConfigError(
                f"{type(self).__name__} requires an API key in env var "
                f"{api_key_env!r}; credentials are read only from the environment, "
                "never from config"
            )
        self._api_key: str = api_key
        self._client = None

    def _client_for(self, httpx):
        """Lazily build (and cache) a per-instance client over the injected transport."""
        if self._client is None:
            self._client = httpx.Client(transport=self._transport, timeout=self.timeout)
        return self._client

    def _request_json(
        self, url: str, body: dict[str, Any], headers: dict[str, str]
    ) -> tuple[dict[str, Any], int]:
        """POST ``body`` to ``url`` with shared retry + typed error mapping.

        Returns ``(parsed_json_body, attempts)``. Maps 401/403 to
        :class:`TargetConfigError` (no retry) and any other failure — exhausted
        429/5xx, 4xx validation, or an unparseable body — to
        :class:`TargetRuntimeError`. The parsed body is the *only* thing handed
        back; headers and the key never leave this method.
        """
        httpx = self._httpx()
        client = self._client_for(httpx)

        def send():
            return client.post(url, json=body, headers=headers)

        response, attempts = request_with_retry(
            send, httpx=httpx, max_retries=self.max_retries
        )
        status = response.status_code
        if status in (401, 403):
            raise TargetConfigError(
                f"{self.name}: authentication failed (HTTP {status}); "
                f"check the key in {self.api_key_env!r}"
            )
        if status >= 400:
            raise TargetRuntimeError(
                f"{self.name}: provider returned HTTP {status} after {attempts} attempt(s)"
            )
        try:
            data = response.json()
        except (ValueError, TypeError) as exc:
            raise TargetRuntimeError(
                f"{self.name}: response body was not valid JSON"
            ) from exc
        if not isinstance(data, dict):
            raise TargetRuntimeError(
                f"{self.name}: expected a JSON object body, got {type(data).__name__}"
            )
        return data, attempts

    def _httpx(self):
        return load_httpx(self.extra)

    def generate(  # pragma: no cover - abstract-ish; subclasses implement
        self, messages: list[Message], tools: list[dict] | None = None
    ) -> Response:
        raise NotImplementedError
