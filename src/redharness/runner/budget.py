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

import contextvars
import threading
from collections.abc import Iterator
from contextlib import contextmanager

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


#: Thread-isolated per-compute usage accumulator. Set by :func:`attempt_usage_scope`
#: around each behavior's ``compute`` and read by :meth:`BudgetedTarget.generate`, so a
#: behavior's stamped usage folds in exactly its own attempts' calls even when computes
#: for other behaviors run concurrently on sibling worker threads. A :class:`ContextVar`
#: is per-thread, so each worker thread sees only the tally it set; the global tally on
#: :class:`QueryBudget` (the run-level budget/total) is unaffected and stays thread-safe.
_attempt_usage: contextvars.ContextVar[UsageTally | None] = contextvars.ContextVar(
    "redharness_attempt_usage", default=None
)


@contextmanager
def attempt_usage_scope() -> Iterator[UsageTally]:
    """Bind a fresh per-compute :class:`UsageTally` for the current thread and yield it.

    Every usage-bearing call made through a :class:`BudgetedTarget` on this thread while
    the scope is active is folded into the yielded tally and nothing else; the previous
    binding is restored on exit, so a reused worker thread never carries usage across
    behaviors.
    """
    tally = UsageTally()
    token = _attempt_usage.set(tally)
    try:
        yield tally
    finally:
        _attempt_usage.reset(token)


class QueryBudget:
    """A running tally of real provider calls, enforced fail-closed at the call site.

    ``max_queries`` of ``None`` means unbounded (the offline default): calls are
    still tallied in ``spent`` but a charge never raises. The same object also owns
    the run's :class:`UsageTally`, so token accounting and the call budget share one
    coherent account charged at the innermost call site.

    A lock guards ``charge``/``record_usage`` so the budget stays a single coherent
    account under the opt-in :class:`ThreadPoolExecutor` path; it stays fail-closed
    (a charge crossing the ceiling raises in whichever worker tripped it).
    """

    def __init__(self, max_queries: int | None, run_id: str = "run") -> None:
        self.max_queries = max_queries
        self.run_id = run_id
        self.spent = 0
        self.usage = UsageTally()
        self._lock = threading.Lock()

    def charge(self, n: int) -> None:
        """Account ``n`` real provider calls; abort fail-closed if over budget."""
        with self._lock:
            self.spent += n
            spent = self.spent
            over = self.max_queries is not None and spent > self.max_queries
        if over:
            raise RunBudgetExceeded(
                f"run {self.run_id!r} exceeded its query budget: used {spent} "
                f"> max_queries {self.max_queries} (aborting fail-closed). The budget "
                "counts real HTTP calls including retries, enforced at the call site"
            )

    def record_usage(self, usage: Usage | None) -> None:
        """Fold a response's normalized token usage into the run-wide tally."""
        with self._lock:
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
        attempt_usage = _attempt_usage.get()
        if attempt_usage is not None:
            attempt_usage.record(response.usage)
        self._budget.charge(response.http_calls)
        return response
