"""Tests for the offline attacks against the deterministic MockTarget."""

from __future__ import annotations

import pytest

from redharness.attacks.static import StaticReplayAttack
from redharness.attacks.template import DEFAULT_TEMPLATES, TemplateJailbreakAttack
from redharness.targets.mock import MockTarget
from tests.conftest import make_behavior


def test_static_replay_single_attempt():
    attack = StaticReplayAttack()
    behavior = make_behavior()
    attempts = attack.run(behavior, MockTarget())
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt.attack_name == "static"
    assert attempt.query_count == 1
    assert attempt.transcript[0].role == "user"
    assert attempt.transcript[-1].role == "assistant"
    assert "can't" in attempt.final_response.lower()  # mock refuses the marker


def test_static_replay_with_system_prompt():
    attack = StaticReplayAttack(system_prompt="be safe")
    attempts = attack.run(make_behavior(), MockTarget())
    assert attempts[0].transcript[0].role == "system"


def test_template_attack_one_attempt_per_template():
    attack = TemplateJailbreakAttack()
    attempts = attack.run(make_behavior(), MockTarget())
    assert len(attempts) == len(DEFAULT_TEMPLATES)
    labels = {a.metadata["template"] for a in attempts}
    assert labels == set(DEFAULT_TEMPLATES)


def test_template_attack_bypass_makes_one_attempt_succeed():
    attack = TemplateJailbreakAttack()
    target = MockTarget(bypass_markers=["ignore the previous framing"])
    attempts = attack.run(make_behavior(), target)
    complied = [a for a in attempts if "can't" not in a.final_response.lower()]
    assert len(complied) == 1
    assert complied[0].metadata["template"] == "prefix_injection"


def test_template_rejects_template_without_placeholder():
    with pytest.raises(ValueError):
        TemplateJailbreakAttack(templates={"bad": "no placeholder here"})


def test_template_explicit_empty_dict_raises():
    # Explicit empty templates is a configuration error, not "use defaults".
    with pytest.raises(ValueError, match="must not be empty"):
        TemplateJailbreakAttack(templates={})


def test_template_none_uses_defaults():
    attack = TemplateJailbreakAttack(templates=None)
    assert set(attack.templates) == set(DEFAULT_TEMPLATES)
