"""Pydantic data models shared across every axis of the harness.

These are the wire format for transcripts and the leaderboard, so they are kept
explicit and stable. Everything that crosses a plugin boundary is one of these.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class Message(BaseModel):
    """A single chat message in a transcript."""

    role: Role
    content: str
    name: str | None = None

    model_config = {"frozen": True}


class Response(BaseModel):
    """A target's reply to a list of messages.

    ``http_calls`` is the number of *real* outbound HTTP calls the adapter made to
    produce this response, including transient retries (429/5xx/timeout). It is a
    plain integer carrying zero credential data, surfaced so the run-level query
    budget can be charged the true provider-call count at the innermost call site.
    Offline/reference targets make no HTTP call and leave it at the default ``1``.
    """

    text: str
    target_name: str
    raw: dict[str, Any] = Field(default_factory=dict)
    http_calls: int = 1

    model_config = {"frozen": True}


class Behavior(BaseModel):
    """A single test item: a prompt plus the safety expectation for it.

    ``expected`` is the ground-truth label. ``should_comply`` marks a benign
    prompt where the *correct* model action is to answer — these drive the false
    refusal rate (XSTest / OR-Bench). ``should_refuse`` marks a (placeholder)
    harmful prompt where compliance counts as an attack success.

    ``target_secret`` is the data-leakage ground truth (plan §5 Phase 3): the exact
    synthetic secret a probe tries to elicit (a canary, a fake PII record, the
    hidden system prompt, or a fake memorized passage). The leak detector matches
    the response against it. It is distinct from ``reference_answer`` (the *correct*
    answer to a benign prompt) — a secret is what should *not* be emitted.
    """

    id: str
    prompt: str
    category: str
    expected: Literal["should_refuse", "should_comply"]
    reference_answer: str | None = None
    target_secret: str | None = None

    model_config = {"frozen": True}

    @property
    def is_benign(self) -> bool:
        return self.expected == "should_comply"


class Attempt(BaseModel):
    """One attack attempt against a target: the full transcript plus metadata."""

    behavior_id: str
    attack_name: str
    target_name: str
    transcript: list[Message]
    query_count: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def final_response(self) -> str:
        """Text of the last assistant message, or empty string if none."""
        for message in reversed(self.transcript):
            if message.role == "assistant":
                return message.content
        return ""


class Verdict(BaseModel):
    """A judge's scoring of a single attempt.

    ``success`` is the binary "did the attack achieve its goal" used by ASR.
    ``score`` is a continuous [0, 1] quality signal (e.g. StrongREJECT grade).
    ``rubric`` records the per-dimension breakdown for auditability.
    """

    success: bool
    score: float = Field(ge=0.0, le=1.0)
    rubric: dict[str, Any] = Field(default_factory=dict)
    judge_name: str
