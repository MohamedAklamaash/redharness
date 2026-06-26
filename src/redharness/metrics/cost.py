"""Cost metrics over the per-behavior token usage stamped by the runner.

The runner folds every provider call's provider-normalized token usage into the
run-wide tally (``runner.budget.UsageTally``) and stamps the per-behavior delta
into ``Attempt.metadata['usage']`` at the single choke point. These metrics read
that stamp; tokens are the primary signal, dollars an optional convenience from a
small, clearly-dated price table.

Both group by behavior (so a behavior whose attack produced several attempts is
counted once, matching the ASR convention) and return ``value=None`` (N/A) when no
attempt carries usage — i.e. every local/offline run, where no real provider was
queried.
"""

from __future__ import annotations

from collections import defaultdict

from redharness.core.metric import Metric, MetricResult, ScoredAttempts
from redharness.core.registry import register_metric

#: Indicative list prices in USD per 1M tokens, as of 2026-06. Keyed by a model-id
#: substring matched against ``Attempt.target_name``; ``(input, output)``. This is a
#: convenience estimate only — verify against your provider's current pricing.
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4": (0.8, 4.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.0, 8.0),
}

PRICE_TABLE_DATE = "2026-06"


def _usage_by_behavior(scored: ScoredAttempts) -> dict[str, tuple[str, dict]]:
    """Map each behavior to ``(target_name, usage)`` for behaviors carrying usage."""
    groups: dict[str, list] = defaultdict(list)
    for behavior, attempt, _ in scored:
        groups[behavior.id].append(attempt)
    out: dict[str, tuple[str, dict]] = {}
    for bid, attempts in groups.items():
        for attempt in attempts:
            usage = attempt.metadata.get("usage")
            if isinstance(usage, dict):
                out[bid] = (attempt.target_name, usage)
                break
    return out


def _token_usage(scored: ScoredAttempts) -> MetricResult:
    """Total input/output tokens across behaviors; N/A when no usage was recorded."""
    per_behavior = _usage_by_behavior(scored)
    if not per_behavior:
        return MetricResult(name="token_usage", value=None, breakdown={"n_behaviors": 0})
    input_tokens = sum((u.get("input_tokens") or 0) for _, u in per_behavior.values())
    output_tokens = sum((u.get("output_tokens") or 0) for _, u in per_behavior.values())
    return MetricResult(
        name="token_usage",
        value=float(input_tokens + output_tokens),
        breakdown={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "n_behaviors": len(per_behavior),
        },
    )


def _price_for(target_name: str) -> tuple[float, float] | None:
    for model, price in PRICES_USD_PER_MTOK.items():
        if model in target_name:
            return price
    return None


def _cost(scored: ScoredAttempts) -> MetricResult:
    """Estimated USD cost from the dated price table; N/A when nothing is priceable.

    Each behavior's tokens are priced by matching its target name against the price
    table. Unpriced models contribute nothing and are reported in the breakdown.
    Returns N/A when no usage is present, or when usage is present but no behavior's
    model is in the table (so an offline run, or one against unpriced local models,
    reports ``—`` rather than a misleading ``$0``).

    Caveat — multi-provider attacks: the stamped per-behavior usage folds every
    provider the attack touched (target, plus the attacker and in-loop judge for
    PAIR/TAP/Crescendo) into one combined token total, and this metric prices that
    whole total at the *target* model's rate. When the attacker/judge run on a
    different (often cheaper) model the dollar figure over- or under-states the true
    spend; treat it as an estimate. The ``token_usage`` metric (a pure token sum) is
    unaffected.
    """
    per_behavior = _usage_by_behavior(scored)
    if not per_behavior:
        return MetricResult(name="cost", value=None, breakdown={"n_behaviors": 0})
    total = 0.0
    priced = 0
    unpriced: set[str] = set()
    for target_name, usage in per_behavior.values():
        price = _price_for(target_name)
        if price is None:
            unpriced.add(target_name)
            continue
        priced += 1
        total += (usage.get("input_tokens") or 0) / 1_000_000 * price[0]
        total += (usage.get("output_tokens") or 0) / 1_000_000 * price[1]
    if priced == 0:
        return MetricResult(
            name="cost",
            value=None,
            breakdown={"n_behaviors": len(per_behavior), "unpriced": sorted(unpriced)},
        )
    return MetricResult(
        name="cost",
        value=round(total, 6),
        breakdown={
            "usd": round(total, 6),
            "price_table_date": PRICE_TABLE_DATE,
            "n_priced": priced,
            "unpriced": sorted(unpriced),
        },
    )


token_usage = Metric("token_usage", _token_usage)
cost = Metric("cost", _cost)

for _metric in (token_usage, cost):
    register_metric(_metric.name)(_metric)
