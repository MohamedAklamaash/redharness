"""Offline tests for the public-benchmark loaders (no network, synthetic fixtures).

Every loader is exercised against a SYNTHETIC ``file://`` CSV written to tmp_path —
no real harmful prompt is committed or fetched. Each loader is checked for: correct
row→Behavior mapping, hash-mismatch raising, and the ``allow_download=False`` gate.
"""

from __future__ import annotations

import hashlib

import pytest

from redharness.core.registry import registry
from redharness.datasets.benchmarks import (
    _PLACEHOLDER_COMMIT,
    AdvBenchDataset,
    HarmBenchDataset,
    JBBBehaviorsDataset,
    ORBenchDataset,
    XSTestDataset,
)
from redharness.errors import DatasetError, DatasetHashMismatch

_ALL_LOADERS = (
    AdvBenchDataset,
    HarmBenchDataset,
    JBBBehaviorsDataset,
    XSTestDataset,
    ORBenchDataset,
)

ADVBENCH_CSV = (
    b"goal,target\n"
    b"PLACEHOLDER advbench prompt one,Sure here\n"
    b"PLACEHOLDER advbench prompt two,Sure here\n"
    b",skipped empty\n"
)
HARMBENCH_CSV = (
    b"Behavior,FunctionalCategory,SemanticCategory\n"
    b"PLACEHOLDER harmbench behavior,standard,cybercrime\n"
)
JBB_CSV = (
    b"Index,Goal,Target,Behavior,Category,Source\n"
    b"0,PLACEHOLDER jbb goal,Sure,Phishing,Privacy,custom\n"
)
XSTEST_CSV = (
    b"id,type,prompt\n"
    b"1,safe_homonyms,PLACEHOLDER benign question,\n"
    b"2,contrast_homonyms,PLACEHOLDER unsafe question,\n"
)
ORBENCH_CSV = (
    b"prompt,category\n"
    b"PLACEHOLDER over-refusal prompt,deception\n"
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dataset(cls, tmp_path, data, sha256=None, allow_download=True):
    path = tmp_path / "fixture.csv"
    path.write_bytes(data)
    return cls(
        url=path.as_uri(),
        sha256=sha256 if sha256 is not None else _sha256(data),
        allow_download=allow_download,
    )


def test_advbench_maps_goal_column(tmp_path):
    ds = _dataset(AdvBenchDataset, tmp_path, ADVBENCH_CSV)
    behaviors = ds.load()
    assert len(behaviors) == 2  # the empty-goal row is skipped
    assert behaviors[0].prompt == "PLACEHOLDER advbench prompt one"
    assert behaviors[0].expected == "should_refuse"
    assert behaviors[0].id == "advbench-0000"
    assert ds.version.startswith("advbench@")


def test_harmbench_maps_behavior_and_semantic_category(tmp_path):
    ds = _dataset(HarmBenchDataset, tmp_path, HARMBENCH_CSV)
    [behavior] = ds.load()
    assert behavior.prompt == "PLACEHOLDER harmbench behavior"
    assert behavior.category == "cybercrime"
    assert behavior.expected == "should_refuse"


def test_jbb_maps_goal_and_category(tmp_path):
    ds = _dataset(JBBBehaviorsDataset, tmp_path, JBB_CSV)
    [behavior] = ds.load()
    assert behavior.prompt == "PLACEHOLDER jbb goal"
    assert behavior.category == "Privacy"
    assert behavior.expected == "should_refuse"


def test_xstest_safe_is_comply_contrast_is_refuse(tmp_path):
    ds = _dataset(XSTestDataset, tmp_path, XSTEST_CSV)
    safe, contrast = ds.load()
    assert safe.expected == "should_comply"  # safe split exercises FRR
    assert contrast.expected == "should_refuse"
    assert safe.category == "safe_homonyms"


def test_orbench_benign_is_comply(tmp_path):
    ds = _dataset(ORBenchDataset, tmp_path, ORBENCH_CSV)
    [behavior] = ds.load()
    assert behavior.expected == "should_comply"  # over-refusal benign -> FRR
    assert behavior.category == "deception"


@pytest.mark.parametrize(
    ("cls", "data"),
    [
        (AdvBenchDataset, ADVBENCH_CSV),
        (HarmBenchDataset, HARMBENCH_CSV),
        (JBBBehaviorsDataset, JBB_CSV),
        (XSTestDataset, XSTEST_CSV),
        (ORBenchDataset, ORBENCH_CSV),
    ],
)
def test_hash_mismatch_raises(tmp_path, cls, data):
    ds = _dataset(cls, tmp_path, data, sha256="0" * 64)
    with pytest.raises(DatasetHashMismatch):
        ds.load()


@pytest.mark.parametrize(
    ("cls", "data"),
    [
        (AdvBenchDataset, ADVBENCH_CSV),
        (HarmBenchDataset, HARMBENCH_CSV),
        (JBBBehaviorsDataset, JBB_CSV),
        (XSTestDataset, XSTEST_CSV),
        (ORBenchDataset, ORBENCH_CSV),
    ],
)
def test_requires_allow_download(tmp_path, cls, data):
    ds = _dataset(cls, tmp_path, data, allow_download=False)
    with pytest.raises(DatasetError, match="allow_download"):
        ds.load()


@pytest.mark.parametrize(
    ("name", "cls"),
    [
        ("advbench", AdvBenchDataset),
        ("harmbench", HarmBenchDataset),
        ("jbb_behaviors", JBBBehaviorsDataset),
        ("xstest", XSTestDataset),
        ("or_bench", ORBenchDataset),
    ],
)
def test_resolvable_by_name(name, cls):
    assert registry.datasets.get(name) is cls


@pytest.mark.parametrize("cls", _ALL_LOADERS)
def test_default_url_is_an_obvious_placeholder(cls):
    """Each shipped DEFAULT_URL must carry the sentinel commit, never a real-looking
    SHA, so a future real-pin PR cannot accidentally ship a fabricated one."""
    assert _PLACEHOLDER_COMMIT in cls.DEFAULT_URL


def test_missing_prompt_column_raises(tmp_path):
    bad = b"target,note\nSure,synthetic\n"
    ds = _dataset(AdvBenchDataset, tmp_path, bad)
    with pytest.raises(DatasetError, match="goal"):
        ds.load()


def test_limit_caps_rows(tmp_path):
    rows = b"goal,target\n" + b"".join(
        f"PLACEHOLDER prompt {i},x\n".encode() for i in range(20)
    )
    path = tmp_path / "advbench.csv"
    path.write_bytes(rows)
    ds = AdvBenchDataset(url=path.as_uri(), sha256=_sha256(rows), allow_download=True, limit=5)
    assert len(ds.load()) == 5


def test_all_empty_rows_raises(tmp_path):
    only_empty = b"goal,target\n,a\n,b\n"
    ds = _dataset(AdvBenchDataset, tmp_path, only_empty)
    with pytest.raises(DatasetError, match="zero behaviors"):
        ds.load()
