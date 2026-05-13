"""A simple on-disk attempt cache keyed by (target, attack, behavior) + params.

Re-running an eval shouldn't re-query a target for combinations already seen. The
cache stores serialized ``Attempt`` lists as JSON under a content key; it is
deterministic and safe to delete (a cold cache just recomputes).

The key folds in a stable hash of the resolved target and attack plugin params, so
two specs that share a ``name`` but differ in ``params`` — or the same ``run_name``
re-run after a param change — never collide and serve stale attempts. This upholds
the reproducibility contract: a cached attempt is reused only when the exact
(names + params + behavior) that produced it recur.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from redharness.core.models import Attempt


def params_hash(params: dict[str, Any]) -> str:
    """A stable sha256 over plugin params, order-independent."""
    canonical = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class AttemptCache:
    """JSON-file cache of attempt lists under ``<dir>/<key>.json``."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(
        target: str,
        target_params_hash: str,
        attack: str,
        attack_params_hash: str,
        behavior_id: str,
        behavior_prompt: str,
    ) -> str:
        digest = hashlib.sha256(
            "\x00".join(
                [
                    target,
                    target_params_hash,
                    attack,
                    attack_params_hash,
                    behavior_id,
                    behavior_prompt,
                ]
            ).encode()
        ).hexdigest()
        return digest[:32]

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(
        self,
        target: str,
        target_params_hash: str,
        attack: str,
        attack_params_hash: str,
        behavior_id: str,
        behavior_prompt: str,
    ) -> list[Attempt] | None:
        path = self._path(
            self._key(
                target,
                target_params_hash,
                attack,
                attack_params_hash,
                behavior_id,
                behavior_prompt,
            )
        )
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        return [Attempt.model_validate(item) for item in payload]

    def put(
        self,
        target: str,
        target_params_hash: str,
        attack: str,
        attack_params_hash: str,
        behavior_id: str,
        behavior_prompt: str,
        attempts: list[Attempt],
    ) -> None:
        path = self._path(
            self._key(
                target,
                target_params_hash,
                attack,
                attack_params_hash,
                behavior_id,
                behavior_prompt,
            )
        )
        path.write_text(json.dumps([a.model_dump() for a in attempts], indent=2))
