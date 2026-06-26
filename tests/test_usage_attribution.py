"""Per-attempt usage attribution must be thread-isolated under --concurrency > 1.

The runner stamps each behavior's ``metadata["usage"]`` from a thread-scoped
accumulator, so a behavior reads exactly its own attempts' tokens even when the
computes for other behaviors run on sibling worker threads at the same time. This
test forces maximal interleaving (a barrier releases all four worker threads into
their generate loops together, with a per-call sleep so their global-tally writes
overlap) and asserts every behavior's stamped usage equals exactly its own tokens
with no cross-attribution, and that the per-behavior totals sum to the run total.

Fully offline: an injected fake target returns deterministic per-call ``usage``;
no network is touched.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from redharness.config import RunConfig
from redharness.core.attack import Attack
from redharness.core.dataset import Dataset
from redharness.core.models import Attempt, Behavior, Message, Response, Usage
from redharness.core.registry import register_attack, register_dataset, register_target
from redharness.core.target import Target
from redharness.runner import Runner

_N = 4
_INPUT_PER_CALL = 1
_OUTPUT_PER_CALL = 2
_START = threading.Barrier(_N)


@register_dataset("_attr_ds")
class _AttrDataset(Dataset):
    name = "_attr_ds"

    @property
    def version(self) -> str:
        return "_attr@0"

    def load(self) -> list[Behavior]:
        return [
            Behavior(
                id=f"b{n}",
                prompt=f"calls={n}",
                category="c",
                expected="should_refuse",
            )
            for n in range(1, _N + 1)
        ]


@register_target("_attr_target")
class _AttrTarget(Target):
    name = "_attr_target"

    def __init__(self, name: str | None = None) -> None:
        self.name = name or "_attr_target"

    def generate(self, messages, tools=None):
        return Response(
            text="Sure, here is help.",
            target_name=self.name,
            usage=Usage(input_tokens=_INPUT_PER_CALL, output_tokens=_OUTPUT_PER_CALL),
        )


@register_attack("_attr_attack")
class _AttrAttack(Attack):
    """Issue exactly ``calls=N`` usage-bearing calls, distinct per behavior.

    All worker threads rendezvous at a barrier before issuing any call, then sleep
    between calls, so the threads' usage-bearing calls interleave maximally. A
    snapshot/diff against the shared global tally would mis-attribute here; the
    thread-scoped accumulator does not.
    """

    name = "_attr_attack"

    def run(self, behavior: Behavior, target: Target) -> list[Attempt]:
        count = int(behavior.prompt.split("=", 1)[1])
        message = Message(role="user", content=behavior.prompt)
        _START.wait(timeout=10)
        text = ""
        for _ in range(count):
            text = target.generate([message]).text
            time.sleep(0.002)
        transcript = [message, Message(role="assistant", content=text)]
        return [
            Attempt(
                behavior_id=behavior.id,
                attack_name=self.name,
                target_name=target.name,
                transcript=transcript,
                query_count=count,
            )
        ]


def _config() -> RunConfig:
    return RunConfig.model_validate(
        {
            "run_name": "attr",
            "concurrency": _N,
            "targets": [{"name": "_attr_target"}],
            "attacks": [{"name": "_attr_attack"}],
            "datasets": [{"name": "_attr_ds"}],
            "judges": [{"name": "refusal_match"}],
            "metrics": ["asr", "token_usage"],
        }
    )


def test_concurrent_usage_is_attributed_per_behavior_without_cross_talk(tmp_path):
    runner = Runner(_config(), tmp_path)
    result = runner.run()

    rows = [
        json.loads(line)
        for line in Path(runner.transcript_path).read_text().splitlines()
        if line
    ]
    stamped = {row["behavior_id"]: row["metadata"]["usage"] for row in rows}

    for n in range(1, _N + 1):
        usage = stamped[f"b{n}"]
        assert usage["input_tokens"] == n * _INPUT_PER_CALL, f"b{n} cross-attributed"
        assert usage["output_tokens"] == n * _OUTPUT_PER_CALL, f"b{n} cross-attributed"

    total_calls = sum(range(1, _N + 1))
    assert sum(u["input_tokens"] for u in stamped.values()) == runner.budget.usage.input_tokens
    assert sum(u["output_tokens"] for u in stamped.values()) == runner.budget.usage.output_tokens
    assert runner.budget.usage.input_tokens == total_calls * _INPUT_PER_CALL
    assert runner.budget.usage.output_tokens == total_calls * _OUTPUT_PER_CALL

    [cell] = result.cells
    assert cell.metrics["token_usage"].breakdown["input_tokens"] == total_calls * _INPUT_PER_CALL
    assert cell.metrics["token_usage"].breakdown["output_tokens"] == total_calls * _OUTPUT_PER_CALL
