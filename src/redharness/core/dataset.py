"""The Dataset axis: loads a versioned, hash-pinned set of behaviors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from redharness.core.models import Behavior


class Dataset(ABC):
    """Loads behaviors and reports a content version.

    ``version`` is recorded next to every leaderboard number so a result is
    always tied to the exact dataset it was measured on (plan §6). Loaders
    verify content by sha256 before yielding behaviors.
    """

    name: str = "dataset"

    @property
    @abstractmethod
    def version(self) -> str:
        """A content-derived version string (e.g. ``demo@<sha256[:12]>``)."""
        raise NotImplementedError

    @abstractmethod
    def load(self) -> list[Behavior]:
        """Return the behaviors, raising on hash mismatch."""
        raise NotImplementedError
