"""Offline mocked-transport tests for the live httpx adapters (no network).

Both adapters are driven through ``httpx.MockTransport`` so the full request →
retry → parse → typed-error path is exercised deterministically without a socket.
"""

from __future__ import annotations

import json
import sys

import pytest

from redharness.core.models import Message
from redharness.errors import TargetConfigError, TargetRuntimeError

httpx = pytest.importorskip("httpx")

from redharness.targets import _http  # noqa: E402
from redharness.targets.anthropic import AnthropicTarget  # noqa: E402
from redharness.targets.openai_compat import (  # noqa: E402
    API_KEY_ENV,
    OpenAICompatTarget,
)

SENTINEL_KEY = "sk-SENTINEL-DO-NOT-LEAK-123"


@pytest.fixture(autouse=True)
def _instant_backoff(monkeypatch):
    """Make retries instant so retry-count tests don't actually sleep."""
    monkeypatch.setattr(_http, "_backoff_seconds", lambda *a, **k: 0.0)


def _openai(monkeypatch, handler, **kwargs) -> OpenAICompatTarget:
    monkeypatch.setenv(API_KEY_ENV, SENTINEL_KEY)
    return OpenAICompatTarget(
        model="gpt-test",
        base_url="https://api.test/v1",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _anthropic(monkeypatch, handler, **kwargs) -> AnthropicTarget:
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL_KEY)
    return AnthropicTarget(transport=httpx.MockTransport(handler), **kwargs)


# --- OpenAI-compatible adapter ------------------------------------------------


def test_openai_happy_path_parses_content_and_usage(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Sure, here is the answer."}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    resp = _openai(monkeypatch, handler).generate([Message(role="user", content="hi")])
    assert resp.text == "Sure, here is the answer."
    assert resp.raw["usage"] == {"prompt_tokens": 7, "completion_tokens": 3}


def test_openai_401_is_config_error(monkeypatch):
    target = _openai(monkeypatch, lambda r: httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(TargetConfigError):
        target.generate([Message(role="user", content="hi")])


def test_openai_retries_then_runtime_error_on_429(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, json={"error": "rate limited"})

    target = _openai(monkeypatch, handler, max_retries=2)
    with pytest.raises(TargetRuntimeError):
        target.generate([Message(role="user", content="hi")])
    assert calls["n"] == 3  # initial + 2 retries


def test_openai_retries_then_succeeds_on_5xx(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    target = _openai(monkeypatch, handler, max_retries=2)
    assert target.generate([Message(role="user", content="hi")]).text == "ok"
    assert calls["n"] == 2


def test_openai_timeout_is_runtime_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectTimeout("timed out")

    target = _openai(monkeypatch, handler, max_retries=1)
    with pytest.raises(TargetRuntimeError):
        target.generate([Message(role="user", content="hi")])


def test_openai_malformed_body_is_runtime_error(monkeypatch):
    target = _openai(monkeypatch, lambda r: httpx.Response(200, content=b"not json"))
    with pytest.raises(TargetRuntimeError):
        target.generate([Message(role="user", content="hi")])


def test_openai_empty_choices_yields_empty_response(monkeypatch):
    target = _openai(monkeypatch, lambda r: httpx.Response(200, json={"choices": []}))
    resp = target.generate([Message(role="user", content="hi")])
    assert resp.text == ""  # no KeyError, a usable empty/blocked response


def test_openai_missing_key_raises_config_error(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    with pytest.raises(TargetConfigError):
        OpenAICompatTarget(model="gpt-test", base_url="https://api.test/v1")


def test_openai_missing_extra_raises_typed(monkeypatch):
    target = _openai(monkeypatch, lambda r: httpx.Response(200, json={"choices": []}))
    monkeypatch.setitem(sys.modules, "httpx", None)  # simulate the extra not installed
    with pytest.raises(TargetConfigError, match="extra"):
        target.generate([Message(role="user", content="hi")])


# --- base_url must be https (cleartext key protection, Security M1) ------------


def _ok_transport():
    return httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})
    )


def test_base_url_rejects_cleartext_remote(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, SENTINEL_KEY)
    with pytest.raises(TargetConfigError, match="https"):
        OpenAICompatTarget(
            model="m", base_url="http://evil.example", transport=_ok_transport()
        )


@pytest.mark.parametrize(
    "base_url",
    ["http://localhost:8000", "http://127.0.0.1:8000", "https://api.example/v1"],
)
def test_base_url_allows_loopback_http_and_any_https(monkeypatch, base_url):
    monkeypatch.setenv(API_KEY_ENV, SENTINEL_KEY)
    target = OpenAICompatTarget(model="m", base_url=base_url, transport=_ok_transport())
    assert target.base_url == base_url.rstrip("/")


# --- Anthropic adapter --------------------------------------------------------


def test_anthropic_empty_messages_after_system_hoist_raises(monkeypatch):
    # A system-only transcript hoists everything out of ``messages``; sending the
    # resulting empty array would 400 upstream, so fail with a clear typed error.
    target = _anthropic(monkeypatch, lambda r: httpx.Response(200, json={"content": []}))
    with pytest.raises(TargetRuntimeError, match="empty"):
        target.generate([Message(role="system", content="only a system prompt")])


def test_anthropic_tool_role_is_unsupported_not_silently_dropped(monkeypatch):
    # A ``tool``-role message has no faithful Messages-API representation here, so it
    # is rejected explicitly rather than dropped (which could empty the array).
    target = _anthropic(monkeypatch, lambda r: httpx.Response(200, json={"content": []}))
    with pytest.raises(TargetRuntimeError, match="unsupported"):
        target.generate(
            [
                Message(role="user", content="hi"),
                Message(role="tool", name="search", content="result"),
            ]
        )





def test_anthropic_request_shape_hoists_system_and_omits_temperature(monkeypatch):
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        captured["headers"] = dict(request.headers)
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "hello"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 2},
            },
        )

    target = _anthropic(monkeypatch, handler, max_tokens=256)
    resp = target.generate(
        [
            Message(role="system", content="be terse"),
            Message(role="user", content="hi"),
            Message(role="system", content="and safe"),
            Message(role="assistant", content="ok"),
        ]
    )
    body = captured["body"]
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert body["system"] == "be terse\nand safe"  # both system msgs hoisted + joined
    assert body["messages"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "ok"},
    ]
    assert body["max_tokens"] == 256
    assert "temperature" not in body  # default model is sampling-unsupported -> omitted
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert resp.text == "hello"
    assert resp.raw["usage"] == {"input_tokens": 5, "output_tokens": 2}


def test_anthropic_temperature_included_only_for_supported_model(monkeypatch):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"content": [{"type": "text", "text": "x"}]})

    # Supported model + explicit temperature -> included.
    _anthropic(monkeypatch, handler, model="claude-sonnet-4-6", temperature=0.5).generate(
        [Message(role="user", content="hi")]
    )
    # Unsupported model + explicit temperature -> omitted (would 400 upstream).
    _anthropic(monkeypatch, handler, model="claude-opus-4-8", temperature=0.5).generate(
        [Message(role="user", content="hi")]
    )
    assert bodies[0]["temperature"] == 0.5
    assert "temperature" not in bodies[1]


def test_anthropic_concatenates_text_blocks(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "part one "},
                    {"type": "thinking", "text": "ignore me"},
                    {"type": "text", "text": "part two"},
                ]
            },
        )

    resp = _anthropic(monkeypatch, handler).generate([Message(role="user", content="hi")])
    assert resp.text == "part one part two"


def test_anthropic_refusal_stop_reason_is_blocked_empty(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"content": [], "stop_reason": "refusal"})

    resp = _anthropic(monkeypatch, handler).generate([Message(role="user", content="hi")])
    assert resp.text == ""  # handled as blocked/empty, never a crash


def test_anthropic_401_is_config_error(monkeypatch):
    target = _anthropic(monkeypatch, lambda r: httpx.Response(401, json={"error": "x"}))
    with pytest.raises(TargetConfigError):
        target.generate([Message(role="user", content="hi")])


def test_anthropic_400_is_runtime_error_without_retry(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    target = _anthropic(monkeypatch, handler, max_retries=2)
    with pytest.raises(TargetRuntimeError):
        target.generate([Message(role="user", content="hi")])
    assert calls["n"] == 1  # 4xx validation is never retried


def test_anthropic_529_retries_then_runtime_error(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(529, json={"error": "overloaded"})

    target = _anthropic(monkeypatch, handler, max_retries=2)
    with pytest.raises(TargetRuntimeError):
        target.generate([Message(role="user", content="hi")])
    assert calls["n"] == 3


def test_anthropic_missing_key_raises_config_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(TargetConfigError):
        AnthropicTarget()


def test_anthropic_missing_extra_raises_typed(monkeypatch):
    target = _anthropic(monkeypatch, lambda r: httpx.Response(200, json={"content": []}))
    monkeypatch.setitem(sys.modules, "httpx", None)
    with pytest.raises(TargetConfigError, match="extra"):
        target.generate([Message(role="user", content="hi")])
