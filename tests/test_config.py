"""Tests for config loading and validation error paths."""

from __future__ import annotations

import pytest
import yaml

from redharness.config import load_config
from redharness.errors import ConfigError


def _write(tmp_path, text: str):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


def _write_dict(tmp_path, **fields):
    return _write(tmp_path, yaml.safe_dump(fields))


def test_load_valid_shorthand_and_longhand(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            """
            run_name: t
            targets: [mock]
            attacks: [static]
            datasets: [demo]
            judges:
              - name: rubric
                params:
                  grader: {name: mock}
            metrics: [asr]
            """,
        )
    )
    assert cfg.targets[0].name == "mock"
    assert cfg.judges[0].params["grader"] == {"name": "mock"}


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


def test_malformed_yaml_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "targets: [mock\nthis: : :"))


def test_non_mapping_root_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "- just\n- a\n- list"))


def test_missing_required_axis_raises(tmp_path):
    # metrics axis omitted entirely.
    with pytest.raises(ConfigError):
        load_config(
            _write_dict(
                tmp_path,
                targets=["mock"],
                attacks=["static"],
                datasets=["demo"],
                judges=["refusal_match"],
            )
        )


def test_empty_axis_list_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(
            _write_dict(
                tmp_path,
                targets=[],
                attacks=["static"],
                datasets=["demo"],
                judges=["refusal_match"],
                metrics=["asr"],
            )
        )


@pytest.mark.parametrize("bad_name", ["../../x", "/etc/passwd", "a/b", "..", ".", "", "a" * 129])
def test_run_name_path_traversal_rejected(tmp_path, bad_name):
    with pytest.raises(ConfigError):
        load_config(
            _write_dict(
                tmp_path,
                run_name=bad_name,
                targets=["mock"],
                attacks=["static"],
                datasets=["demo"],
                judges=["refusal_match"],
                metrics=["asr"],
            )
        )


@pytest.mark.parametrize("good_name", ["smoke", "run-1", "run_1.v2", "ABC.123"])
def test_run_name_safe_slug_accepted(tmp_path, good_name):
    cfg = load_config(
        _write_dict(
            tmp_path,
            run_name=good_name,
            targets=["mock"],
            attacks=["static"],
            datasets=["demo"],
            judges=["refusal_match"],
            metrics=["asr"],
        )
    )
    assert cfg.run_name == good_name


def test_unknown_config_key_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(
            _write_dict(
                tmp_path,
                targets=["mock"],
                attacks=["static"],
                datasets=["demo"],
                judges=["refusal_match"],
                metrics=["asr"],
                bogus=1,
            )
        )
