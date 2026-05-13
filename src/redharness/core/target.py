"""The Target axis: an adapter over a model under test."""

from __future__ import annotations

from abc import ABC, abstractmethod

from redharness.core.models import Message, Response


class Target(ABC):
    """A model under test.

    Implementations wrap an API or local model and expose a single ``generate``
    call. ``name`` is the identifier recorded in transcripts and on the
    leaderboard, so it must be stable across runs.
    """

    name: str = "target"

    @abstractmethod
    def generate(self, messages: list[Message], tools: list[dict] | None = None) -> Response:
        """Return the model's reply to ``messages``.

        ``tools`` is reserved for the injection/agentic surface and ignored by
        the offline jailbreak targets.
        """
        raise NotImplementedError
