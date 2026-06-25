"""Tests for the bundled demo dataset and the remote fetch-and-verify loader."""

from __future__ import annotations

import json

import pytest

from redharness.datasets.demo import DemoDataset
from redharness.datasets.remote import RemoteDataset
from redharness.errors import DatasetError, DatasetHashMismatch

GOOD_PAYLOAD = json.dumps(
    {"behaviors": [{"id": "x1", "prompt": "p", "category": "c", "expected": "should_refuse"}]}
).encode()


def test_demo_dataset_loads_and_verifies():
    ds = DemoDataset()
    behaviors = ds.load()
    assert 45 <= len(behaviors) <= 55
    assert ds.version.startswith("redharness-demo@")
    # Mix of harmful refusal probes and benign should-comply items.
    expectations = {b.expected for b in behaviors}
    assert expectations == {"should_refuse", "should_comply"}
    # The harmful probes are spread across several realistic harm categories.
    harmful_categories = {b.category for b in behaviors if b.expected == "should_refuse"}
    assert len(harmful_categories) >= 6


def test_demo_dataset_excludes_cbrn_and_contains_no_real_identifiers():
    # The bundled set is responsibly synthetic: no CBRN/explosives synthesis content,
    # and no real-looking emails/URLs anywhere in the prompts.
    banned = ("@gmail", "@yahoo", "@outlook", "http://", "https://")
    cbrn = ("bioweapon", "nerve agent", "sarin", "anthrax", "enrich uranium", "pipe bomb")
    for behavior in DemoDataset().load():
        lowered = behavior.prompt.lower()
        assert not any(tok in lowered for tok in banned)
        assert not any(tok in lowered for tok in cbrn)


def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def test_remote_loads_from_file_url(tmp_path):
    path = tmp_path / "behaviors.json"
    path.write_bytes(GOOD_PAYLOAD)
    ds = RemoteDataset(
        name="t", url=path.as_uri(), sha256=_sha256(GOOD_PAYLOAD), allow_download=True
    )
    behaviors = ds.load()
    assert behaviors[0].id == "x1"
    assert ds.version == f"t@{_sha256(GOOD_PAYLOAD)[:12]}"


def test_remote_hash_mismatch_raises(tmp_path):
    path = tmp_path / "behaviors.json"
    path.write_bytes(GOOD_PAYLOAD)
    ds = RemoteDataset(name="t", url=path.as_uri(), sha256="0" * 64, allow_download=True)
    with pytest.raises(DatasetHashMismatch):
        ds.load()


def test_remote_refuses_http_without_allow_download():
    ds = RemoteDataset(name="t", url="https://example.com/x.json", sha256="0" * 64)
    with pytest.raises(DatasetError):
        ds.load()


def test_remote_empty_dataset_raises(tmp_path):
    payload = json.dumps({"behaviors": []}).encode()
    path = tmp_path / "empty.json"
    path.write_bytes(payload)
    ds = RemoteDataset(
        name="t", url=path.as_uri(), sha256=_sha256(payload), allow_download=True
    )
    with pytest.raises(DatasetError):
        ds.load()


# --- Finding 6: RemoteDataset is registered under "remote" and resolvable -----


def test_remote_dataset_resolvable_by_name():
    from redharness.core.registry import registry

    cls = registry.datasets.get("remote")
    assert cls is RemoteDataset
    assert "remote" in registry.datasets.names()


def test_remote_built_via_config_stays_inert_offline():
    # Resolved by name through the builder, it must still refuse network without opt-in.
    from redharness.config import PluginSpec
    from redharness.runner.build import build_dataset

    ds = build_dataset(
        PluginSpec(
            name="remote",
            params={"name": "t", "url": "https://example.com/x.json", "sha256": "0" * 64},
        )
    )
    with pytest.raises(DatasetError):
        ds.load()


# --- Finding 7: hardened fetch (SSRF / file:// gating / scheme allow-list) -----


def test_remote_rejects_disallowed_scheme():
    ds = RemoteDataset(
        name="t", url="ftp://example.com/x.json", sha256="0" * 64, allow_download=True
    )
    with pytest.raises(DatasetError, match="scheme"):
        ds.load()


def test_remote_file_requires_allow_download(tmp_path):
    path = tmp_path / "behaviors.json"
    path.write_bytes(GOOD_PAYLOAD)
    ds = RemoteDataset(name="t", url=path.as_uri(), sha256=_sha256(GOOD_PAYLOAD))
    with pytest.raises(DatasetError, match="allow_download"):
        ds.load()


def test_remote_caps_response_size(tmp_path, monkeypatch):
    import redharness.datasets.remote as remote_mod

    monkeypatch.setattr(remote_mod, "_MAX_BYTES", 8)
    path = tmp_path / "big.json"
    path.write_bytes(b"x" * 100)
    ds = RemoteDataset(
        name="t", url=path.as_uri(), sha256="0" * 64, allow_download=True
    )
    with pytest.raises(DatasetError, match="size cap"):
        ds.load()


def test_remote_blocks_private_ip(monkeypatch):
    # Force host resolution to a private address; fetch must be refused (SSRF).
    import redharness.datasets.remote as remote_mod

    def fake_getaddrinfo(host, *args, **kwargs):
        return [(2, 1, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(remote_mod.socket, "getaddrinfo", fake_getaddrinfo)
    ds = RemoteDataset(
        name="t", url="https://internal.example/x.json", sha256="0" * 64, allow_download=True
    )
    with pytest.raises(DatasetError, match="non-public"):
        ds.load()
