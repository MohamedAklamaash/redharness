"""Hash-pinned loader for bundled injection scenario suites.

Mirrors the dataset loader's fetch-and-verify contract (plan §7): a manifest pins
each suite file by sha256, and loading recomputes the hash and refuses to yield
scenarios on mismatch. Suites are benign — they demonstrate the injection mechanism
with sentinel attacker goals; real AgentDojo / InjecAgent corpora are not bundled.
"""

from __future__ import annotations

import json
from importlib import resources

from redharness.datasets.loader import sha256_hex, short_version, verify_hash
from redharness.errors import DatasetError
from redharness.scenarios.suite import ScenarioSpec, SuiteScenario

_DATA_PACKAGE = "redharness.scenarios.data"


def _read_data_file(filename: str) -> bytes:
    return (resources.files(_DATA_PACKAGE) / filename).read_bytes()


def parse_specs(data: bytes) -> list[ScenarioSpec]:
    """Parse a suite JSON payload into validated :class:`ScenarioSpec` models."""
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise DatasetError(f"scenario suite is not valid JSON: {exc}") from exc
    raw = payload.get("scenarios")
    if not isinstance(raw, list):
        raise DatasetError("scenario suite payload missing a 'scenarios' list")
    return [ScenarioSpec.model_validate(item) for item in raw]


class BundledSuite:
    """Loads and hash-verifies one bundled scenario suite by manifest key."""

    def __init__(self, suite: str) -> None:
        manifest = json.loads(_read_data_file("manifest.json"))
        entry = manifest.get(suite)
        if entry is None:
            known = ", ".join(sorted(k for k in manifest if not k.startswith("_")))
            raise DatasetError(f"unknown scenario suite {suite!r}; available: {known}")
        self.suite = suite
        self._entry = entry
        self._data = _read_data_file(entry["file"])

    @property
    def version(self) -> str:
        return short_version(self._entry["name"], self._entry["sha256"])

    def load(self) -> list[SuiteScenario]:
        verify_hash(self._data, self._entry["sha256"])
        specs = parse_specs(self._data)
        if not specs:
            raise DatasetError(f"scenario suite {self.suite!r} is empty")
        return [SuiteScenario(spec) for spec in specs]


def compute_sha256(suite_file: str) -> str:
    """Helper used by the data-build step to (re)compute a suite file's hash."""
    return sha256_hex(_read_data_file(suite_file))
