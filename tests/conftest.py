"""Shared fixtures and helpers for the test suite."""

from __future__ import annotations

import redharness.plugins  # noqa: F401  (populate registries for every test)
from redharness.core.models import Attempt, Behavior, Message


def make_behavior(
    bid: str = "b1",
    prompt: str = "[HARMFUL-PLACEHOLDER] do the forbidden thing",
    category: str = "harmful-placeholder",
    expected: str = "should_refuse",
) -> Behavior:
    return Behavior(id=bid, prompt=prompt, category=category, expected=expected)


def make_attempt(
    behavior: Behavior,
    response: str,
    attack_name: str = "static",
    target_name: str = "mock",
    query_count: int = 1,
    template: str | None = None,
) -> Attempt:
    transcript = [
        Message(role="user", content=behavior.prompt),
        Message(role="assistant", content=response),
    ]
    metadata = {"template": template} if template else {}
    return Attempt(
        behavior_id=behavior.id,
        attack_name=attack_name,
        target_name=target_name,
        transcript=transcript,
        query_count=query_count,
        metadata=metadata,
    )
