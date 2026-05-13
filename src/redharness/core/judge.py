"""The Judge axis: scores an attempt against the behavior's expectation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from redharness.core.models import Attempt, Behavior, Verdict


class Judge(ABC):
    """Scores whether an attempt achieved the attacker's goal.

    Different judges disagree on the same transcript — quantifying that
    disagreement is an explicit research goal (plan §8), so the judge name is
    recorded on every verdict and leaderboard cell.
    """

    name: str = "judge"

    @abstractmethod
    def score(self, behavior: Behavior, attempt: Attempt) -> Verdict:
        """Return a verdict for ``attempt`` given ``behavior``'s expectation."""
        raise NotImplementedError
