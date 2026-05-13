"""Tests for the typed plugin registry."""

from __future__ import annotations

import pytest

from redharness.core.registry import Registry, registry
from redharness.errors import RegistryError


def test_register_and_resolve():
    reg: Registry = Registry("widget")

    @reg.register("alpha")
    class Alpha:
        pass

    assert reg.get("alpha") is Alpha
    assert reg.names() == ["alpha"]


def test_unknown_name_raises_with_available_list():
    reg: Registry = Registry("widget")

    @reg.register("alpha")
    class Alpha:
        pass

    with pytest.raises(RegistryError) as exc:
        reg.get("missing")
    assert "alpha" in str(exc.value)


def test_duplicate_registration_same_class_is_idempotent():
    reg: Registry = Registry("widget")

    class Alpha:
        pass

    reg.register("alpha")(Alpha)
    reg.register("alpha")(Alpha)  # same object -> allowed
    assert reg.get("alpha") is Alpha


def test_duplicate_registration_different_class_raises():
    reg: Registry = Registry("widget")

    @reg.register("alpha")
    class Alpha:
        pass

    with pytest.raises(RegistryError):

        @reg.register("alpha")
        class Beta:
            pass


def test_builtin_plugins_are_registered():
    assert "mock" in registry.targets.names()
    assert {"static", "template"} <= set(registry.attacks.names())
    assert "demo" in registry.datasets.names()
    assert {"refusal_match", "rubric"} <= set(registry.judges.names())
    assert {"asr", "frr", "strongreject_score"} <= set(registry.metrics.names())
