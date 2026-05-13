"""Tests for shared dataset parsing helpers."""

from __future__ import annotations

import pytest

from redharness.datasets.loader import parse_behaviors, sha256_hex, short_version
from redharness.errors import DatasetError


def test_parse_invalid_json_raises():
    with pytest.raises(DatasetError):
        parse_behaviors(b"{not json")


def test_parse_missing_behaviors_list_raises():
    with pytest.raises(DatasetError):
        parse_behaviors(b'{"items": []}')


def test_short_version_truncates_hash():
    digest = sha256_hex(b"abc")
    assert short_version("ds", digest) == f"ds@{digest[:12]}"
