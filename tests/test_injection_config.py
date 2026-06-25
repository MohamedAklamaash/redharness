"""Config-mode validation for the injection surface."""

from __future__ import annotations

import pytest

from redharness.config import RunConfig


def _base(**overrides) -> dict:
    cfg = {
        "run_name": "c",
        "targets": [{"name": "reference_agent"}],
        "judges": [{"name": "injection_detector"}],
        "metrics": ["injection_success_rate"],
    }
    cfg.update(overrides)
    return cfg


def test_injection_mode_detected():
    cfg = RunConfig.model_validate(
        _base(injections=[{"name": "direct_injection"}], scenarios=[{"name": "bundled"}])
    )
    assert cfg.mode == "injection"


def test_jailbreak_mode_detected():
    cfg = RunConfig.model_validate(
        _base(attacks=[{"name": "static"}], datasets=[{"name": "demo"}])
    )
    assert cfg.mode == "jailbreak"


def test_mixed_modes_rejected():
    with pytest.raises(ValueError, match="mixes modes"):
        RunConfig.model_validate(
            _base(
                attacks=[{"name": "static"}],
                datasets=[{"name": "demo"}],
                scenarios=[{"name": "bundled"}],
                injections=[{"name": "direct_injection"}],
            )
        )


def test_injection_mode_requires_injections():
    with pytest.raises(ValueError, match="requires both 'injections' and 'scenarios'"):
        RunConfig.model_validate(_base(scenarios=[{"name": "bundled"}]))


def test_no_mode_configured_rejected():
    with pytest.raises(ValueError, match="jailbreak mode requires"):
        RunConfig.model_validate(_base())


def test_unknown_top_level_field_rejected():
    with pytest.raises(ValueError):
        RunConfig.model_validate(_base(scenariosss=[{"name": "bundled"}]))


def test_max_steps_bounds_validated():
    with pytest.raises(ValueError):
        RunConfig.model_validate(
            _base(
                injections=[{"name": "direct_injection"}],
                scenarios=[{"name": "bundled"}],
                max_steps=0,
            )
        )
