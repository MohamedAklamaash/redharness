"""The StrongREJECT forbidden-prompt set (Souly et al. 2024, arXiv:2402.10260).

StrongREJECT ships as CSV (``forbidden_prompt``, ``category``, ...). We do NOT
commit any raw harmful prompts; this loader fetches them from the canonical,
commit-SHA-pinned source and verifies the content by sha256 — reusing the hardened
:class:`~redharness.datasets.remote.RemoteDataset` fetch machinery (opt-in
``allow_download``, scheme allow-list, SSRF and size caps). It stays inert in the
offline slice because every fetch requires ``allow_download=True``.

The CSV rows are mapped to :class:`Behavior` objects: ``forbidden_prompt`` becomes
the ``prompt``, ``category`` is preserved, a stable index-based ``id`` is
synthesised, and ``expected`` is fixed to ``should_refuse`` (these are all harmful
probes). The small 50-item subset is supported via ``subset='small'``.
"""

from __future__ import annotations

import csv
import io

from redharness.core.models import Behavior
from redharness.core.registry import register_dataset
from redharness.datasets.loader import verify_hash
from redharness.datasets.remote import RemoteDataset
from redharness.errors import DatasetError

# Commit-SHA-pinned canonical source for the small subset. The sha256 below is a
# placeholder: real downloads supply the verified hash (and tests pass their own
# url + hash against a synthetic file:// CSV), so no harmful text is committed here.
SMALL_SUBSET_URL = (
    "https://raw.githubusercontent.com/alexandrasouly/strongreject/"
    "3eb0f7a8b3e0f9f3a0e4e6c8a1b2c3d4e5f60718/strongreject_dataset/"
    "strongreject_small_dataset.csv"
)
SMALL_SUBSET_SIZE = 50
_PLACEHOLDER_SHA256 = "0" * 64


@register_dataset("strongreject")
class StrongRejectDataset(RemoteDataset):
    """Fetch-and-verify the StrongREJECT CSV, mapping rows to behaviors."""

    def __init__(
        self,
        url: str = SMALL_SUBSET_URL,
        sha256: str = _PLACEHOLDER_SHA256,
        allow_download: bool = False,
        subset: str = "small",
        timeout: float = 30.0,
        name: str = "strongreject",
    ) -> None:
        if subset != "small":
            raise DatasetError(
                f"StrongRejectDataset only supports the 'small' subset, got {subset!r}"
            )
        self.subset = subset
        self.limit = SMALL_SUBSET_SIZE
        super().__init__(
            name=name,
            url=url,
            sha256=sha256,
            allow_download=allow_download,
            timeout=timeout,
        )

    def load(self) -> list[Behavior]:
        data = self._fetch()  # inherited: scheme allow-list, SSRF, size cap, opt-in
        verify_hash(data, self.sha256)
        behaviors = _parse_strongreject_csv(data, self.limit)
        if not behaviors:
            raise DatasetError(f"StrongREJECT dataset {self.name!r} parsed to zero behaviors")
        return behaviors


def _parse_strongreject_csv(data: bytes, limit: int) -> list[Behavior]:
    """Map StrongREJECT CSV rows to behaviors, capped at ``limit`` items."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DatasetError(f"StrongREJECT CSV is not valid UTF-8: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "forbidden_prompt" not in reader.fieldnames:
        raise DatasetError("StrongREJECT CSV is missing a 'forbidden_prompt' column")
    behaviors: list[Behavior] = []
    for index, row in enumerate(reader):
        prompt = (row.get("forbidden_prompt") or "").strip()
        if not prompt:
            continue
        category = (row.get("category") or "uncategorized").strip() or "uncategorized"
        behaviors.append(
            Behavior(
                id=f"strongreject-{index:04d}",
                prompt=prompt,
                category=category,
                expected="should_refuse",
            )
        )
        if len(behaviors) >= limit:
            break
    return behaviors
