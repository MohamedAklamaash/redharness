"""Re-score a finished run's transcripts under multiple judges and quantify disagreement.

The motivating finding (plan §8): on AdvBench x PAIR the ``refusal_match`` judge
reported ASR 1.0 while StrongREJECT reported 0.15 — the headline number is a
property of the *judge*, not only the model. This module loads a run's
``transcripts.jsonl``, re-scores every attempt under each requested judge, and
reports each judge's success rate plus the pairwise raw agreement and Cohen's kappa
between judges (Cohen 1960), writing a small ``judge_agreement.json`` next to the
transcripts.

Judges are built through the same :func:`~redharness.runner.build.build_judge`
nesting the runner uses, so a grader-backed judge (rubric / strongreject) is
constructed with an injected grader target — an offline ``reference`` grader by
default, which keeps the analysis fully deterministic and network-free.
"""

from __future__ import annotations

import inspect
import json
from itertools import combinations
from pathlib import Path

from pydantic import BaseModel, Field

from redharness.config import PluginSpec
from redharness.core.models import Attempt, Behavior
from redharness.core.registry import registry
from redharness.errors import RedharnessError
from redharness.metrics.agreement import cohen_kappa
from redharness.runner.build import build_judge


class PairwiseAgreement(BaseModel):
    """Agreement between two judges over the same attempts."""

    judge_a: str
    judge_b: str
    raw_agreement: float
    cohen_kappa: float


class JudgeAgreementReport(BaseModel):
    """Per-judge success rates plus pairwise agreement over one run's transcripts."""

    run_dir: str
    n_attempts: int
    judges: list[str]
    asr: dict[str, float] = Field(default_factory=dict)
    pairwise: list[PairwiseAgreement] = Field(default_factory=list)


def judge_spec(name: str, grader: str = "reference") -> PluginSpec:
    """Build a judge :class:`PluginSpec`, injecting a grader sub-spec when required.

    A judge whose constructor declares a ``grader`` parameter (rubric, strongreject)
    is given ``{"grader": {"name": <grader>}}`` so :func:`build_judge` materialises a
    grader target for it; judges without that parameter (refusal_match, leak_detector)
    get bare params. Introspecting the signature avoids a hard-coded name list.
    """
    cls = registry.judges.get(name)
    params: dict = {}
    if "grader" in inspect.signature(cls.__init__).parameters:
        params["grader"] = {"name": grader}
    return PluginSpec(name=name, params=params)


def _load_attempts(run_dir: Path) -> list[Attempt]:
    path = run_dir / "transcripts.jsonl"
    if not path.exists():
        raise RedharnessError(f"no transcripts.jsonl under run dir {run_dir}")
    attempts = [
        Attempt.model_validate(json.loads(line))
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    if not attempts:
        raise RedharnessError(f"transcripts.jsonl under {run_dir} is empty")
    return attempts


def _behavior_from_attempt(attempt: Attempt) -> Behavior:
    """Reconstruct the minimal behavior a judge needs from a persisted attempt.

    The transcript carries the request (first user turn) and the response, which is
    all the offline judges read; the ground-truth ``expected`` label is not needed to
    decide attack *success* (that is the judge's own call), so it defaults to
    ``should_refuse``.
    """
    prompt = next(
        (m.content for m in attempt.transcript if m.role == "user"),
        attempt.final_response,
    )
    return Behavior(
        id=attempt.behavior_id,
        prompt=prompt,
        category="reconstructed",
        expected="should_refuse",
    )


def run_judge_agreement(
    run_dir: Path,
    judge_specs: list[PluginSpec],
    write: bool = True,
) -> JudgeAgreementReport:
    """Re-score ``run_dir``'s transcripts under each judge and report disagreement.

    Returns a :class:`JudgeAgreementReport` and, when ``write`` is set, also writes
    it to ``run_dir/judge_agreement.json``. Requires at least two judges so a
    pairwise comparison exists.
    """
    if len(judge_specs) < 2:
        raise RedharnessError("judge-agreement needs at least two judges to compare")
    run_dir = Path(run_dir)
    attempts = _load_attempts(run_dir)
    behaviors = [_behavior_from_attempt(a) for a in attempts]

    judges = [build_judge(spec) for spec in judge_specs]
    names = [judge.name for judge in judges]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise RedharnessError(
            "judge-agreement needs distinct judges, but these are repeated: "
            f"{', '.join(repeated)}; pass each judge at most once"
        )
    labels: dict[str, list[bool]] = {
        name: [judge.score(b, a).success for b, a in zip(behaviors, attempts, strict=True)]
        for name, judge in zip(names, judges, strict=True)
    }

    asr = {name: sum(col) / len(col) for name, col in labels.items()}
    pairwise: list[PairwiseAgreement] = []
    for name_a, name_b in combinations(names, 2):
        a, b = labels[name_a], labels[name_b]
        raw = sum(1 for x, y in zip(a, b, strict=True) if x == y) / len(a)
        pairwise.append(
            PairwiseAgreement(
                judge_a=name_a,
                judge_b=name_b,
                raw_agreement=round(raw, 6),
                cohen_kappa=round(cohen_kappa(a, b), 6),
            )
        )

    report = JudgeAgreementReport(
        run_dir=str(run_dir),
        n_attempts=len(attempts),
        judges=names,
        asr={k: round(v, 6) for k, v in asr.items()},
        pairwise=pairwise,
    )
    if write:
        (run_dir / "judge_agreement.json").write_text(report.model_dump_json(indent=2))
    return report
