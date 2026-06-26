"""The run-level query budget and the target wrapper that enforces it.

The budget counts *real* outbound provider calls — including transient retries
(429/5xx/timeout), which :class:`~redharness.core.models.Response.http_calls`
surfaces — and is charged at the innermost call site (each ``generate``). This is
the single, coherent account for the whole run:

  * single-turn jailbreak/leakage attacks charge ``http_calls`` for their one call;
  * PAIR charges every outbound call it makes (attacker + target + in-loop judge),
    because each of those providers is wrapped, so the run aborts *mid-behavior* the
    instant the ceiling is crossed — bounded overshoot is now only the in-flight
    retries of a single call, never a whole behavior;
  * cache HITS never reach ``generate`` and so are never charged.

Enforcement is fail-closed: the moment ``spent`` exceeds ``max_queries`` the charge
raises :class:`~redharness.errors.RunBudgetExceeded`, aborting the run rather than
silently overspending against a paid provider.
"""

from __future__ import annotations

from redharness.core.models import Message, Response, Usage
from redharness.core.target import Target
from redharness.errors import RunBudgetExceeded


class UsageTally:
    """A running, provider-normalized token total shared across wrapped targets.

    The run has many :class:`BudgetedTarget` instances (cell target, PAIR attacker,
    in-loop judge grader) all wrapping the *same* tally, so per-behavior usage folds
    in every provider an attack touched. A response with no ``usage`` (offline
    targets, failed/retried calls that never produced a body) contributes nothing
    and is not counted as a usage-bearing call.
    """

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    def record(self, usage: Usage | None) -> None:
        if usage is None:
            return
        self.calls += 1
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0

    def snapshot(self) -> tuple[int, int, int]:
        return (self.input_tokens, self.output_tokens, self.calls)


class QueryBudget:
    """A running tally of real provider calls, enforced fail-closed at the call site.

    ``max_queries`` of ``None`` means unbounded (the offline default): calls are
    still tallied in ``spent`` but a charge never raises. The same object also owns
    the run's :class:`UsageTally`, so token accounting and the call budget share one
    coherent account charged at the innermost call site.
    """

    def __init__(self, max_queries: int | None, run_id: str = "run") -> None:
        self.max_queries = max_queries
        self.run_id = run_id
        self.spent = 0
        self.usage = UsageTally()

    def charge(self, n: int) -> None:
        """Account ``n`` real provider calls; abort fail-closed if over budget."""
        self.spent += n
        if self.max_queries is not None and self.spent > self.max_queries:
            raise RunBudgetExceeded(
                f"run {self.run_id!r} exceeded its query budget: used {self.spent} "
                f"> max_queries {self.max_queries} (aborting fail-closed). The budget "
                "counts real HTTP calls including retries, enforced at the call site"
            )

    def record_usage(self, usage: Usage | None) -> None:
        """Fold a response's normalized token usage into the run-wide tally."""
        self.usage.record(usage)


class BudgetedTarget(Target):
    """Transparent :class:`Target` wrapper that charges the budget per real call.

    Delegates ``name`` to the inner target so transcripts and cache keys are
    unchanged, and charges ``response.http_calls`` after each ``generate`` so the
    retry-inclusive real-call count folds into the run budget at the innermost call
    site. Constructed per run (never persisted), so wrapping is invisible to the
    content-based cache key, which the runner computes from the *raw* target.
    """

    def __init__(self, inner: Target, budget: QueryBudget) -> None:
        self._inner = inner
        self._budget = budget

    @property
    def name(self) -> str:
        return self._inner.name

    def generate(
        self, messages: list[Message], tools: list[dict] | None = None
    ) -> Response:
        response = self._inner.generate(messages, tools)
        self._budget.record_usage(response.usage)
        self._budget.charge(response.http_calls)
        return response
