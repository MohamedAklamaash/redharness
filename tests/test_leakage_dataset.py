"""Tests for the bundled, hash-pinned leakage probe suite."""

from __future__ import annotations

import pytest

import redharness.datasets.leakage as leakage_mod
from redharness.datasets.leakage import LeakageDataset
from redharness.errors import DatasetError, DatasetHashMismatch, LeakageConfigError

_CATEGORIES = {"canary", "pii", "system_prompt", "extraction"}


def test_leakage_suite_loads_and_verifies():
    ds = LeakageDataset()
    probes = ds.load()
    assert 8 <= len(probes) <= 12
    assert ds.version.startswith("redharness-leakage-demo@")
    # Every category is represented and every probe carries its ground-truth secret.
    assert {p.category for p in probes} == _CATEGORIES
    for probe in probes:
        assert probe.target_secret


def test_leakage_suite_secrets_are_synthetic():
    for probe in LeakageDataset().load():
        secret = probe.target_secret or ""
        # Obvious fakes only: sentinels / example.invalid PII.
        assert (
            secret.startswith(("CANARY-", "SYSTEM-SECRET-", "MEMORIZED-PASSAGE-"))
            or "example.invalid" in secret
        )


def test_leakage_suite_resolvable_by_name():
    from redharness.core.registry import registry

    assert registry.datasets.get("leakage_demo") is LeakageDataset
    assert "leakage_demo" in registry.datasets.names()


def test_leakage_hash_mismatch_raises(monkeypatch):
    ds = LeakageDataset()
    tampered = dict(ds._manifest)
    tampered["sha256"] = "0" * 64
    monkeypatch.setattr(ds, "_manifest", tampered)
    with pytest.raises(DatasetHashMismatch):
        ds.load()


def test_missing_target_secret_rejected(monkeypatch):
    payload = (
        b'{"behaviors": [{"id": "x", "prompt": "p", "category": "canary", '
        b'"expected": "should_refuse"}]}'
    )
    import hashlib

    sha = hashlib.sha256(payload).hexdigest()
    ds = LeakageDataset()
    monkeypatch.setattr(ds, "_data", payload)
    monkeypatch.setattr(ds, "_manifest", {**ds._manifest, "sha256": sha})
    with pytest.raises(LeakageConfigError, match="target_secret"):
        ds.load()


def test_bad_category_rejected(monkeypatch):
    payload = (
        b'{"behaviors": [{"id": "x", "prompt": "p", "category": "nonsense", '
        b'"expected": "should_refuse", "target_secret": "S"}]}'
    )
    import hashlib

    sha = hashlib.sha256(payload).hexdigest()
    ds = LeakageDataset()
    monkeypatch.setattr(ds, "_data", payload)
    monkeypatch.setattr(ds, "_manifest", {**ds._manifest, "sha256": sha})
    with pytest.raises(LeakageConfigError, match="category"):
        ds.load()


def test_manifest_hash_matches_data_file():
    # The committed manifest must pin the committed data file (no silent drift).
    from redharness.datasets.loader import sha256_hex

    ds = LeakageDataset()
    assert sha256_hex(ds._data) == ds._manifest["sha256"]


def test_empty_suite_raises(monkeypatch):
    payload = b'{"behaviors": []}'
    import hashlib

    sha = hashlib.sha256(payload).hexdigest()
    ds = LeakageDataset()
    monkeypatch.setattr(ds, "_data", payload)
    monkeypatch.setattr(ds, "_manifest", {**ds._manifest, "sha256": sha})
    with pytest.raises(DatasetError):
        ds.load()


def test_data_package_constant_points_at_datasets():
    assert leakage_mod._DATA_PACKAGE == "redharness.datasets.data"
