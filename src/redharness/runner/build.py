"""Construct plugin instances from validated config specs.

This is the one place that turns YAML names into live objects, so it owns the few
wiring quirks — notably that :class:`RubricJudge` needs a grader ``Target``
injected. The grader is itself a target spec under the judge's ``grader`` param,
which keeps the offline path deterministic (the smoke config points it at the
``reference`` target).
"""

from __future__ import annotations

import redharness.plugins  # noqa: F401  (populate registries before name resolution)
from redharness.config import PluginSpec
from redharness.core.attack import Attack
from redharness.core.dataset import Dataset
from redharness.core.judge import Judge
from redharness.core.metric import Metric
from redharness.core.registry import registry
from redharness.core.target import Target

# Attribute under which a built plugin carries the spec it was constructed from,
# so the runner can fold the resolved params into the cache key (the spec is not
# part of the plugin's own interface, hence a private attribute set here).
SPEC_ATTR = "_redharness_spec"


def build_target(spec: PluginSpec) -> Target:
    instance = registry.targets.get(spec.name)(**spec.params)
    setattr(instance, SPEC_ATTR, spec)
    return instance


def build_attack(spec: PluginSpec) -> Attack:
    """Build an attack, materialising nested ``attacker``/``judge`` sub-specs.

    Search attacks (e.g. ``pair``) take an injected attacker :class:`Target` and a
    :class:`Judge` rather than instantiating them internally — same pattern as
    :func:`build_judge`'s ``grader``. We pop the sub-specs, build them, and pass
    the live objects to the constructor. The *original* spec (with the nested
    dicts intact) is recorded under ``SPEC_ATTR`` so the runner's cache key folds
    in the attacker model / ``max_iters`` and busts when they change.
    """
    params = dict(spec.params)
    attacker_spec = params.pop("attacker", None)
    if attacker_spec is not None:
        params["attacker"] = build_target(PluginSpec.model_validate(attacker_spec))
    judge_spec = params.pop("judge", None)
    if judge_spec is not None:
        params["judge"] = build_judge(PluginSpec.model_validate(judge_spec))
    instance = registry.attacks.get(spec.name)(**params)
    setattr(instance, SPEC_ATTR, spec)
    return instance


def build_dataset(spec: PluginSpec) -> Dataset:
    return registry.datasets.get(spec.name)(**spec.params)


def build_judge(spec: PluginSpec) -> Judge:
    """Build a judge, materialising a nested grader target if requested."""
    params = dict(spec.params)
    grader_spec = params.pop("grader", None)
    if grader_spec is not None:
        params["grader"] = build_target(PluginSpec.model_validate(grader_spec))
    return registry.judges.get(spec.name)(**params)


def build_metric(name: str) -> Metric:
    return registry.metrics.get(name)


def build_injection(spec: PluginSpec):
    """Build an injection attack (plan §5 Phase 2)."""
    instance = registry.injections.get(spec.name)(**spec.params)
    setattr(instance, SPEC_ATTR, spec)
    return instance


def build_scenario_source(spec: PluginSpec):
    """Build a scenario-suite source (e.g. the hash-pinned ``bundled`` loader)."""
    instance = registry.scenarios.get(spec.name)(**spec.params)
    setattr(instance, SPEC_ATTR, spec)
    return instance
