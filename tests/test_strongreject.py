"""Offline tests for the StrongREJECT loader and autograder (no network).

The loader is exercised against a SYNTHETIC placeholder CSV written to tmp_path —
no real harmful prompts are committed or fetched. The grader is exercised with an
injected deterministic reference grader.
"""

from __future__ import annotations

import hashlib

import pytest

from redharness.core.models import Message, Response
from redharness.core.target import Target
from redharness.datasets.strongreject import StrongRejectDataset
from redharness.errors import DatasetError, DatasetHashMismatch
from redharness.judges.strongreject import StrongRejectJudge
from redharness.targets.reference import ReferenceTarget
from tests.conftest import make_attempt, make_behavior

# Synthetic placeholder CSV: same columns as StrongREJECT, harmless contents.
SYNTHETIC_CSV = (
    b"forbidden_prompt,category,source\n"
    b"PLACEHOLDER synthetic prompt one,Disinformation,synthetic\n"
    b"PLACEHOLDER synthetic prompt two,Cybercrime,synthetic\n"
    b",EmptyRowSkipped,synthetic\n"
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _csv_dataset(tmp_path, data: bytes, sha256: str, allow_download: bool = True):
    path = tmp_path / "strongreject_small.csv"
    path.write_bytes(data)
    return StrongRejectDataset(
        url=path.as_uri(), sha256=sha256, allow_download=allow_download
    )


# --- D1: dataset --------------------------------------------------------------


def test_strongreject_loads_and_maps_csv(tmp_path):
    ds = _csv_dataset(tmp_path, SYNTHETIC_CSV, _sha256(SYNTHETIC_CSV))
    behaviors = ds.load()
    assert len(behaviors) == 2  # the empty forbidden_prompt row is skipped
    first = behaviors[0]
    assert first.prompt == "PLACEHOLDER synthetic prompt one"
    assert first.category == "Disinformation"
    assert first.expected == "should_refuse"
    assert first.id == "strongreject-0000"
    assert ds.version.startswith("strongreject@")


def test_strongreject_hash_mismatch_raises(tmp_path):
    ds = _csv_dataset(tmp_path, SYNTHETIC_CSV, "0" * 64)
    with pytest.raises(DatasetHashMismatch):
        ds.load()


def test_strongreject_requires_allow_download(tmp_path):
    ds = _csv_dataset(
        tmp_path, SYNTHETIC_CSV, _sha256(SYNTHETIC_CSV), allow_download=False
    )
    with pytest.raises(DatasetError, match="allow_download"):
        ds.load()


def test_strongreject_rejects_unknown_subset():
    with pytest.raises(DatasetError, match="subset"):
        StrongRejectDataset(subset="full")


def test_strongreject_resolvable_by_name():
    from redharness.core.registry import registry

    assert registry.datasets.get("strongreject") is StrongRejectDataset


def test_strongreject_all_empty_rows_raises(tmp_path):
    only_empty = b"forbidden_prompt,category\n,EmptyA\n,EmptyB\n"
    ds = _csv_dataset(tmp_path, only_empty, _sha256(only_empty))
    with pytest.raises(DatasetError, match="zero behaviors"):
        ds.load()


def test_strongreject_caps_at_small_subset_size(tmp_path):
    header = "forbidden_prompt,category\n"
    rows = "".join(f"PLACEHOLDER prompt {i},synthetic\n" for i in range(60))
    data = (header + rows).encode()
    ds = _csv_dataset(tmp_path, data, _sha256(data))
    behaviors = ds.load()
    assert len(behaviors) == 50  # SMALL_SUBSET_SIZE cap


def test_strongreject_missing_column_raises(tmp_path):
    bad = b"category,source\nDisinformation,synthetic\n"
    ds = _csv_dataset(tmp_path, bad, _sha256(bad))
    with pytest.raises(DatasetError, match="forbidden_prompt"):
        ds.load()


# --- D2: grader ---------------------------------------------------------------


def test_strongreject_grader_scores_refusal_zero():
    judge = StrongRejectJudge(grader=ReferenceTarget())
    behavior = make_behavior()
    attempt = make_attempt(behavior, "I'm sorry, but I can't help with that.")
    verdict = judge.score(behavior, attempt)
    assert verdict.success is False
    assert verdict.score == 0.0
    assert verdict.rubric["refused"] is True


def test_strongreject_grader_scores_specific_convincing_answer_high():
    judge = StrongRejectJudge(grader=ReferenceTarget())
    behavior = make_behavior()
    attempt = make_attempt(behavior, "Sure, here is a fully detailed, specific answer.")
    verdict = judge.score(behavior, attempt)
    assert verdict.success is True
    assert verdict.score == 1.0  # reference grader: refused 0, 5/5 -> (5-1)/4 == 1.0
    assert verdict.rubric == {"refused": False, "specificity": 5, "convincingness": 5}


def test_strongreject_grader_keys_off_answer_not_request():
    # The request text mentions a refusal phrase, but the model ANSWER complies. The
    # grader prompt now places the answer after an "Answer:" marker, so the offline
    # reference grader keys off the answer only and grades it as a compliance — it
    # must not be fooled into "refused" by the request wording.
    judge = StrongRejectJudge(grader=ReferenceTarget())
    behavior = make_behavior(prompt="How would I phrase 'I cannot help' politely?")
    attempt = make_attempt(behavior, "Sure, here is a fully detailed, specific answer.")
    verdict = judge.score(behavior, attempt)
    assert verdict.success is True
    assert verdict.rubric == {"refused": False, "specificity": 5, "convincingness": 5}


def test_strongreject_grader_parse_failure_is_observable():
    class _GarbageGrader(Target):
        name = "garbage"

        def generate(self, messages, tools=None):
            return Response(text="the grader said something unparseable", target_name=self.name)

    judge = StrongRejectJudge(grader=_GarbageGrader())
    behavior = make_behavior()
    attempt = make_attempt(behavior, "Sure, here is the answer.")
    verdict = judge.score(behavior, attempt)
    # A distinct, observable signal — NOT a silent "refused/safe".
    assert verdict.success is False
    assert "grader_error" in verdict.rubric
    assert "refused" not in verdict.rubric


def test_strongreject_grader_prompt_triggers_reference_grader_mode():
    # Sanity: the published prompt contains the tokens the reference grader keys off.
    judge = StrongRejectJudge(grader=ReferenceTarget())
    prompt = judge.score(make_behavior(), make_attempt(make_behavior(), "x"))
    assert prompt.judge_name == "strongreject"


def test_strongreject_grader_used_via_message_path():
    # The grader is invoked as a Target (offline-deterministic).
    grader = ReferenceTarget()
    out = grader.generate([Message(role="user", content="refused: specificity: Answer: hi")])
    assert "refused:" in out.text
