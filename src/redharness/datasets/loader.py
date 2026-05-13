"""Shared dataset parsing and hash verification.

Keeping the hash check in one place means both the bundled and remote loaders
get the same "fetch-and-verify, never silently mutate" guarantee (plan §7).
"""

from __future__ import annotations

import hashlib
import json

from redharness.core.models import Behavior
from redharness.errors import DatasetError, DatasetHashMismatch


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_hash(data: bytes, expected_sha256: str) -> None:
    """Raise :class:`DatasetHashMismatch` if ``data`` does not hash as expected."""
    actual = sha256_hex(data)
    if actual != expected_sha256:
        raise DatasetHashMismatch(
            f"dataset hash mismatch: expected {expected_sha256}, got {actual}"
        )


def parse_behaviors(data: bytes) -> list[Behavior]:
    """Parse a behavior-set JSON payload into validated ``Behavior`` models."""
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise DatasetError(f"dataset is not valid JSON: {exc}") from exc
    raw_behaviors = payload.get("behaviors")
    if not isinstance(raw_behaviors, list):
        raise DatasetError("dataset payload missing a 'behaviors' list")
    return [Behavior.model_validate(item) for item in raw_behaviors]


def short_version(name: str, sha256: str) -> str:
    """A leaderboard-friendly version string, e.g. ``redharness-demo@11f909c5b617``."""
    return f"{name}@{sha256[:12]}"
