"""The dataset fetch builds a certifi-backed SSL context when certifi is importable.

Offline: no network. A ``file://`` fixture proves the fetch still works, and the
SSL-context builder is asserted to consult ``certifi`` when present and to fall back
to the stdlib default when it is not.
"""

from __future__ import annotations

import hashlib
import ssl
import sys

import redharness.datasets.remote as remote
from redharness.datasets.benchmarks import AdvBenchDataset

_CSV = b"goal,target\nPLACEHOLDER advbench prompt,Sure here\n"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_ssl_context_uses_certifi_when_importable(monkeypatch):
    seen = {}

    class _FakeCertifi:
        @staticmethod
        def where() -> str:
            seen["called"] = True
            return ssl.get_default_verify_paths().cafile or ""

    monkeypatch.setitem(sys.modules, "certifi", _FakeCertifi)
    ctx = remote._ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert seen.get("called") is True


def test_ssl_context_falls_back_without_certifi(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _no_certifi(name, *args, **kwargs):
        if name == "certifi":
            raise ImportError("no certifi")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_certifi)
    ctx = remote._ssl_context()
    assert isinstance(ctx, ssl.SSLContext)


def test_file_fetch_still_works_with_ssl_change(tmp_path):
    path = tmp_path / "advbench.csv"
    path.write_bytes(_CSV)
    ds = AdvBenchDataset(url=path.as_uri(), sha256=_sha256(_CSV), allow_download=True)
    [behavior] = ds.load()
    assert behavior.prompt == "PLACEHOLDER advbench prompt"
