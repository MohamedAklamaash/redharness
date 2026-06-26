"""Thin fetch-and-verify loaders for the public red-teaming benchmark sets.

Each loader subclasses the hardened :class:`~redharness.datasets.remote.RemoteDataset`
(opt-in ``allow_download``, scheme allow-list, SSRF and size caps) and adds only a
source URL, a placeholder ``sha256``, and a row→:class:`Behavior` mapping. No raw
prompt is committed and the shipped defaults are inert: each ``DEFAULT_URL`` carries
an obvious placeholder commit segment (``REPLACE_WITH_VERIFIED_COMMIT_SHA``) and the
committed ``sha256`` is the self-evident placeholder ``"0" * 64``. Before enabling
``allow_download`` the operator MUST pin a verified commit-SHA source URL *and* its
matching ``sha256``; the placeholder hash fails closed, so no silent fetch can
succeed against the default URL. Offline tests drive every loader against a synthetic
``file://`` CSV fixture.

Forbidden-prompt sets (AdvBench, HarmBench, JBB-Behaviors) map to
``expected="should_refuse"``; the over-refusal sets (XSTest's safe split, OR-Bench)
map benign prompts to ``expected="should_comply"`` so the false-refusal-rate metric
is exercised. See ``CONTRIBUTING.md`` for the per-dataset license/provenance table.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable

from redharness.core.models import Behavior
from redharness.core.registry import register_dataset
from redharness.datasets.loader import verify_hash
from redharness.datasets.remote import RemoteDataset
from redharness.errors import DatasetError

_PLACEHOLDER_SHA256 = "0" * 64

#: Obvious, non-resolving stand-in for the commit segment of each ``DEFAULT_URL``.
#: It is visually impossible to mistake for a verified pin: an operator MUST replace
#: it (and the placeholder ``sha256``) with a real verified commit-SHA before turning
#: on ``allow_download``. Asserted by the loader tests so a real-pin PR cannot ship a
#: fabricated SHA by accident.
_PLACEHOLDER_COMMIT = "REPLACE_WITH_VERIFIED_COMMIT_SHA"

Label = Callable[[dict[str, str]], str] | str


def _behaviors_from_csv(
    data: bytes,
    *,
    dataset: str,
    prompt_col: str,
    id_prefix: str,
    label: Label,
    category_col: str | None = None,
    default_category: str = "uncategorized",
    limit: int | None = None,
) -> list[Behavior]:
    """Map CSV rows to behaviors, skipping empty prompts and capping at ``limit``."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DatasetError(f"{dataset} CSV is not valid UTF-8: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or prompt_col not in reader.fieldnames:
        raise DatasetError(f"{dataset} CSV is missing a {prompt_col!r} column")
    behaviors: list[Behavior] = []
    for index, row in enumerate(reader):
        prompt = (row.get(prompt_col) or "").strip()
        if not prompt:
            continue
        category = default_category
        if category_col:
            category = (row.get(category_col) or "").strip() or default_category
        expected = label(row) if callable(label) else label
        behaviors.append(
            Behavior(
                id=f"{id_prefix}-{index:04d}",
                prompt=prompt,
                category=category,
                expected=expected,
            )
        )
        if limit is not None and len(behaviors) >= limit:
            break
    return behaviors


class _BenchmarkDataset(RemoteDataset):
    """Shared load() scaffold: fetch (inherited hardening), verify hash, map rows."""

    dataset_label: str = "benchmark"

    def __init__(
        self,
        url: str,
        sha256: str = _PLACEHOLDER_SHA256,
        allow_download: bool = False,
        timeout: float = 30.0,
        name: str = "benchmark",
        limit: int | None = None,
    ) -> None:
        self.limit = limit
        super().__init__(
            name=name,
            url=url,
            sha256=sha256,
            allow_download=allow_download,
            timeout=timeout,
        )

    def _map_rows(self, data: bytes) -> list[Behavior]:  # pragma: no cover - overridden
        raise NotImplementedError

    def load(self) -> list[Behavior]:
        data = self._fetch()
        verify_hash(data, self.sha256)
        behaviors = self._map_rows(data)
        if not behaviors:
            raise DatasetError(
                f"{self.dataset_label} dataset {self.name!r} parsed to zero behaviors"
            )
        return behaviors


@register_dataset("advbench")
class AdvBenchDataset(_BenchmarkDataset):
    """AdvBench harmful behaviors (Zou et al. 2023, ``data/advbench``).

    CSV columns ``goal,target``; the ``goal`` is the forbidden prompt.
    """

    dataset_label = "AdvBench"
    DEFAULT_URL = (
        "https://raw.githubusercontent.com/llm-attacks/llm-attacks/"
        f"{_PLACEHOLDER_COMMIT}/data/advbench/harmful_behaviors.csv"
    )

    def __init__(self, url: str = DEFAULT_URL, name: str = "advbench", **kwargs) -> None:
        super().__init__(url=url, name=name, **kwargs)

    def _map_rows(self, data: bytes) -> list[Behavior]:
        return _behaviors_from_csv(
            data,
            dataset=self.dataset_label,
            prompt_col="goal",
            id_prefix="advbench",
            label="should_refuse",
            default_category="advbench",
            limit=self.limit,
        )


@register_dataset("harmbench")
class HarmBenchDataset(_BenchmarkDataset):
    """HarmBench standard behaviors (Mazeika et al. 2024, ``behavior_datasets``).

    CSV columns ``Behavior,FunctionalCategory,SemanticCategory,...``.
    """

    dataset_label = "HarmBench"
    DEFAULT_URL = (
        "https://raw.githubusercontent.com/centerforaisafety/HarmBench/"
        f"{_PLACEHOLDER_COMMIT}/data/behavior_datasets/"
        "harmbench_behaviors_text_all.csv"
    )

    def __init__(self, url: str = DEFAULT_URL, name: str = "harmbench", **kwargs) -> None:
        super().__init__(url=url, name=name, **kwargs)

    def _map_rows(self, data: bytes) -> list[Behavior]:
        return _behaviors_from_csv(
            data,
            dataset=self.dataset_label,
            prompt_col="Behavior",
            id_prefix="harmbench",
            label="should_refuse",
            category_col="SemanticCategory",
            default_category="harmbench",
            limit=self.limit,
        )


@register_dataset("jbb_behaviors")
class JBBBehaviorsDataset(_BenchmarkDataset):
    """JBB-Behaviors harmful set (Chao et al. 2024, JailbreakBench).

    CSV columns ``Index,Goal,Target,Behavior,Category,Source``; ``Goal`` is the
    forbidden prompt and ``Category`` the harm category. The canonical source is the
    ``JailbreakBench/JBB-Behaviors`` Hugging Face dataset (``data/harmful-behaviors.csv``);
    the older ``jailbreakbench`` GitHub package path no longer ships the CSV.
    """

    dataset_label = "JBB-Behaviors"
    DEFAULT_URL = (
        "https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors/resolve/"
        f"{_PLACEHOLDER_COMMIT}/data/harmful-behaviors.csv"
    )

    def __init__(self, url: str = DEFAULT_URL, name: str = "jbb_behaviors", **kwargs) -> None:
        super().__init__(url=url, name=name, **kwargs)

    def _map_rows(self, data: bytes) -> list[Behavior]:
        return _behaviors_from_csv(
            data,
            dataset=self.dataset_label,
            prompt_col="Goal",
            id_prefix="jbb",
            label="should_refuse",
            category_col="Category",
            default_category="jbb",
            limit=self.limit,
        )


def _xstest_label(row: dict[str, str]) -> str:
    """XSTest ``contrast_*`` types are the unsafe split; the rest are benign."""
    kind = (row.get("type") or "").strip().lower()
    return "should_refuse" if kind.startswith("contrast") else "should_comply"


@register_dataset("xstest")
class XSTestDataset(_BenchmarkDataset):
    """XSTest exaggerated-safety suite (Röttger et al. 2024).

    CSV columns ``id,type,prompt,...``; the safe split maps to ``should_comply``
    (a refusal there is an over-refusal), the ``contrast_*`` split to
    ``should_refuse``.
    """

    dataset_label = "XSTest"
    DEFAULT_URL = (
        "https://raw.githubusercontent.com/paul-rottger/xstest/"
        f"{_PLACEHOLDER_COMMIT}/xstest_prompts.csv"
    )

    def __init__(self, url: str = DEFAULT_URL, name: str = "xstest", **kwargs) -> None:
        super().__init__(url=url, name=name, **kwargs)

    def _map_rows(self, data: bytes) -> list[Behavior]:
        return _behaviors_from_csv(
            data,
            dataset=self.dataset_label,
            prompt_col="prompt",
            id_prefix="xstest",
            label=_xstest_label,
            category_col="type",
            default_category="xstest",
            limit=self.limit,
        )


@register_dataset("or_bench")
class ORBenchDataset(_BenchmarkDataset):
    """OR-Bench over-refusal benchmark (Cui et al. 2024).

    CSV columns ``prompt,category``; the benign over-refusal prompts map to
    ``should_comply`` so the false-refusal-rate metric is exercised.
    """

    dataset_label = "OR-Bench"
    DEFAULT_URL = (
        "https://huggingface.co/datasets/bench-llm/or-bench/resolve/"
        f"{_PLACEHOLDER_COMMIT}/or-bench-hard-1k.csv"
    )

    def __init__(self, url: str = DEFAULT_URL, name: str = "or_bench", **kwargs) -> None:
        super().__init__(url=url, name=name, **kwargs)

    def _map_rows(self, data: bytes) -> list[Behavior]:
        return _behaviors_from_csv(
            data,
            dataset=self.dataset_label,
            prompt_col="prompt",
            id_prefix="orbench",
            label="should_comply",
            category_col="category",
            default_category="or-bench",
            limit=self.limit,
        )
