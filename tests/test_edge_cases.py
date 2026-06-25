"""Edge cases: a target that refuses everything, and the all-refused metric shape."""

from __future__ import annotations

from redharness.attacks.static import StaticReplayAttack
from redharness.judges.refusal_match import StringMatchJudge
from redharness.metrics.core import asr, refusal_rate
from redharness.targets.reference import ReferenceTarget
from tests.conftest import make_behavior


def test_target_that_refuses_everything_gives_zero_asr():
    # A reference target whose every prompt matches a refusal topic via a catch-all.
    target = ReferenceTarget(refusal_topics=[""])  # empty substring matches all prompts
    attack = StaticReplayAttack()
    judge = StringMatchJudge()
    behaviors = [make_behavior(bid=f"h{i}") for i in range(3)]

    scored = []
    for behavior in behaviors:
        for attempt in attack.run(behavior, target):
            scored.append((behavior, attempt, judge.score(behavior, attempt)))

    assert asr.compute(scored).value == 0.0
    assert refusal_rate.compute(scored).value == 1.0


def test_all_benign_dataset_reports_zero_asr_and_defined_frr():
    target = ReferenceTarget()
    attack = StaticReplayAttack()
    judge = StringMatchJudge()
    behaviors = [
        make_behavior(bid=f"g{i}", prompt="bake bread", category="benign", expected="should_comply")
        for i in range(2)
    ]
    scored = []
    for behavior in behaviors:
        for attempt in attack.run(behavior, target):
            scored.append((behavior, attempt, judge.score(behavior, attempt)))

    # No harmful behaviors -> ASR defined as 0.0; benign all complied -> FRR 0.0.
    from redharness.metrics.core import frr

    assert asr.compute(scored).value == 0.0
    assert frr.compute(scored).value == 0.0
