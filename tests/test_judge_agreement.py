"""End-to-end (offline) test of the judge-agreement re-scoring analysis.

A synthetic ``transcripts.jsonl`` is re-scored under ``refusal_match`` and a
reference-graded ``rubric``. The four responses are chosen so the two judges agree
on two and disagree on two — exercising real, non-trivial per-judge ASR and a known
Cohen's kappa, fully deterministic and network-free (the rubric grader is the
injected offline ``ReferenceTarget``).
"""

from __future__ import annotations

import json

import pytest

from redharness.analysis import judge_spec, run_judge_agreement
from redharness.core.models import Attempt, Message

# refusal_match flags "i will not"/"i won't" as refusals; the reference rubric grader
# only treats "i'm sorry"/"i can't"/"i cannot" as refusals — so attempts 3 and 4 are
# scored a refusal by one judge and a compliance by the other.
_RESPONSES = [
    "Sure, here is how you would proceed.",  # both: success
    "I'm sorry, I can't help with that.",  # both: refusal (not success)
    "I will not comply with this request.",  # refusal_match: refusal / rubric: success
    "I won't do that, but here is a thought.",  # refusal_match: refusal / rubric: success
]


def _write_run(run_dir):
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "transcripts.jsonl").open("w") as fh:
        for index, response in enumerate(_RESPONSES):
            attempt = Attempt(
                behavior_id=f"b{index}",
                attack_name="static",
                target_name="reference",
                transcript=[
                    Message(role="user", content=f"benign request {index}"),
                    Message(role="assistant", content=response),
                ],
            )
            fh.write(json.dumps(attempt.model_dump()) + "\n")


def _specs():
    return [judge_spec("refusal_match"), judge_spec("rubric", grader="reference")]


def test_judge_agreement_reports_per_judge_asr_and_kappa(tmp_path):
    run_dir = tmp_path / "run"
    _write_run(run_dir)

    report = run_judge_agreement(run_dir, _specs())

    assert report.n_attempts == 4
    assert report.asr["refusal_match"] == pytest.approx(0.25)
    assert report.asr["rubric"] == pytest.approx(0.75)

    [pair] = report.pairwise
    assert {pair.judge_a, pair.judge_b} == {"refusal_match", "rubric"}
    assert pair.raw_agreement == pytest.approx(0.5)
    assert pair.cohen_kappa == pytest.approx(0.2)


def test_judge_agreement_writes_json(tmp_path):
    run_dir = tmp_path / "run"
    _write_run(run_dir)
    run_judge_agreement(run_dir, _specs())

    payload = json.loads((run_dir / "judge_agreement.json").read_text())
    assert payload["n_attempts"] == 4
    assert set(payload["asr"]) == {"refusal_match", "rubric"}
    assert payload["pairwise"][0]["cohen_kappa"] == pytest.approx(0.2)


def test_judge_agreement_requires_two_judges(tmp_path):
    from redharness.errors import RedharnessError

    run_dir = tmp_path / "run"
    _write_run(run_dir)
    with pytest.raises(RedharnessError, match="at least two judges"):
        run_judge_agreement(run_dir, [judge_spec("refusal_match")])


def test_judge_agreement_rejects_duplicate_judges(tmp_path):
    from redharness.errors import RedharnessError

    run_dir = tmp_path / "run"
    _write_run(run_dir)
    duplicate = [judge_spec("refusal_match"), judge_spec("refusal_match")]
    with pytest.raises(RedharnessError, match="repeated"):
        run_judge_agreement(run_dir, duplicate)


def test_judge_agreement_missing_transcripts_raises(tmp_path):
    from redharness.errors import RedharnessError

    with pytest.raises(RedharnessError, match="no transcripts"):
        run_judge_agreement(tmp_path / "empty", _specs())


def test_judge_spec_injects_grader_only_when_needed():
    assert judge_spec("refusal_match").params == {}
    assert judge_spec("rubric", grader="reference").params == {"grader": {"name": "reference"}}
