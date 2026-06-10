"""The bundled, hash-verified synthetic data-leakage probe suite (plan §5 Phase 3).

Reuses the ``Dataset`` axis: each probe is a :class:`Behavior` whose
``target_secret`` is the ground-truth synthetic secret a leaky model would emit
and the leak detector matches against. Planting a secret is the *target's* job
(``LeakyMockTarget`` config); *knowing* the planted secret is the *behavior's* job
(``target_secret``) — exactly the canary bookkeeping of a real extraction eval
(Carlini et al. 2019, "The Secret Sharer", arXiv:1802.08232).

The manifest pins the data file by sha256; loading recomputes the hash and refuses
to yield probes on mismatch, so a tampered probe file fails loudly.
"""

from __future__ import annotations

import json
from importlib import resources

from redharness.core.dataset import Dataset
from redharness.core.models import Behavior
from redharness.core.registry import register_dataset
from redharness.datasets.loader import parse_behaviors, short_version, verify_hash
from redharness.errors import DatasetError, LeakageConfigError

_DATA_PACKAGE = "redharness.datasets.data"
_LEAKAGE_CATEGORIES = frozenset({"canary", "pii", "system_prompt", "extraction"})


def _read_data_file(filename: str) -> bytes:
    return (resources.files(_DATA_PACKAGE) / filename).read_bytes()


@register_dataset("leakage_demo")
class LeakageDataset(Dataset):
    """A tiny synthetic leakage probe set verified against its bundled manifest."""

    name = "leakage_demo"

    def __init__(self) -> None:
        manifest_raw = _read_data_file("leakage_manifest.json")
        self._manifest = json.loads(manifest_raw)
        self._data = _read_data_file(self._manifest["file"])

    @property
    def version(self) -> str:
        return short_version(self._manifest["name"], self._manifest["sha256"])

    def load(self) -> list[Behavior]:
        verify_hash(self._data, self._manifest["sha256"])
        behaviors = parse_behaviors(self._data)
        if not behaviors:
            raise DatasetError("leakage_demo dataset is empty")
        for behavior in behaviors:
            if not behavior.target_secret:
                raise LeakageConfigError(
                    f"leakage probe {behavior.id!r} is missing its 'target_secret' "
                    "ground truth; a leakage behavior must carry the secret to detect"
                )
            if behavior.category not in _LEAKAGE_CATEGORIES:
                raise LeakageConfigError(
                    f"leakage probe {behavior.id!r} has category {behavior.category!r}; "
                    f"expected one of {sorted(_LEAKAGE_CATEGORIES)}"
                )
        return behaviors
