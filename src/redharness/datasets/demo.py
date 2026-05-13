"""The bundled, hash-verified demo dataset shipped inside the package."""

from __future__ import annotations

import json
from importlib import resources

from redharness.core.dataset import Dataset
from redharness.core.models import Behavior
from redharness.core.registry import register_dataset
from redharness.datasets.loader import (
    parse_behaviors,
    short_version,
    verify_hash,
)
from redharness.errors import DatasetError

_DATA_PACKAGE = "redharness.datasets.data"


def _read_data_file(filename: str) -> bytes:
    return (resources.files(_DATA_PACKAGE) / filename).read_bytes()


@register_dataset("demo")
class DemoDataset(Dataset):
    """A tiny benign behavior set verified against its bundled manifest.

    The manifest pins the data file by sha256; loading recomputes the hash and
    refuses to yield behaviors if it does not match, so a tampered or truncated
    data file fails loudly rather than silently skewing results.
    """

    name = "demo"

    def __init__(self) -> None:
        manifest_raw = _read_data_file("manifest.json")
        self._manifest = json.loads(manifest_raw)
        self._data = _read_data_file(self._manifest["file"])

    @property
    def version(self) -> str:
        return short_version(self._manifest["name"], self._manifest["sha256"])

    def load(self) -> list[Behavior]:
        verify_hash(self._data, self._manifest["sha256"])
        behaviors = parse_behaviors(self._data)
        if not behaviors:
            raise DatasetError("demo dataset is empty")
        return behaviors
