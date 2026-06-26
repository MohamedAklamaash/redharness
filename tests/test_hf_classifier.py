"""The HF-classifier judge: plumbing-tested with a stub (no weights, no download).

The classifier callable is dependency-injected so the full verdict path runs offline
with no ``transformers`` import. The presets, the ``trust_remote_code`` default, and
the offline-import guarantee are asserted.
"""

from __future__ import annotations

import sys

from redharness.core.registry import registry
from redharness.judges.hf_classifier import HFClassifierJudge
from tests.conftest import make_attempt, make_behavior


def test_stub_classifier_llama_guard_unsafe_is_success():
    judge = HFClassifierJudge(preset="llama_guard", classifier=lambda _t: "unsafe\nS1")
    behavior = make_behavior()
    verdict = judge.score(behavior, make_attempt(behavior, "here is the harmful content"))
    assert verdict.success is True
    assert verdict.score == 1.0
    assert verdict.judge_name == "hf_classifier"
    assert verdict.rubric["preset"] == "llama_guard"


def test_stub_classifier_llama_guard_safe_is_not_success():
    judge = HFClassifierJudge(preset="llama_guard", classifier=lambda _t: "safe")
    behavior = make_behavior()
    verdict = judge.score(behavior, make_attempt(behavior, "I cannot help with that."))
    assert verdict.success is False
    assert verdict.score == 0.0


def test_yes_no_preset():
    judge = HFClassifierJudge(preset="yes_no", classifier=lambda _t: "Yes, it is harmful.")
    behavior = make_behavior()
    assert judge.score(behavior, make_attempt(behavior, "x")).success is True
    judge_no = HFClassifierJudge(preset="yes_no", classifier=lambda _t: "No.")
    assert judge_no.score(behavior, make_attempt(behavior, "x")).success is False


def test_injected_parse_fn_overrides_preset():
    judge = HFClassifierJudge(
        parse_fn=lambda raw: (raw == "HIT", 0.5),
        classifier=lambda _t: "HIT",
    )
    behavior = make_behavior()
    verdict = judge.score(behavior, make_attempt(behavior, "x"))
    assert verdict.success is True
    assert verdict.score == 0.5


def test_trust_remote_code_defaults_false_and_is_recorded():
    judge = HFClassifierJudge(classifier=lambda _t: "safe")
    assert judge.trust_remote_code is False
    behavior = make_behavior()
    verdict = judge.score(behavior, make_attempt(behavior, "x"))
    assert verdict.rubric["trust_remote_code"] is False

    strict = HFClassifierJudge(classifier=lambda _t: "safe", trust_remote_code=True)
    assert strict.trust_remote_code is True


def test_unknown_preset_raises():
    import pytest

    from redharness.errors import RedharnessError

    with pytest.raises(RedharnessError, match="preset"):
        HFClassifierJudge(preset="does_not_exist")


def test_judge_is_registered():
    assert registry.judges.get("hf_classifier") is HFClassifierJudge


def test_module_import_does_not_pull_in_transformers():
    # Importing the judge module (already imported via plugins) must not import the
    # heavy dependency — only constructing a non-injected judge and scoring would.
    assert "transformers" not in sys.modules


def test_lazy_pipeline_is_built_once_and_passes_trust_remote_code(monkeypatch):
    # Drive the non-injected loader path with a FAKE transformers module (no weights,
    # no download): it must build the pipeline once, cache it, and honor the flag.
    import types

    calls = {"built": 0, "ran": 0}

    def fake_pipeline(task, model, trust_remote_code):
        calls["built"] += 1
        calls["model"] = model
        calls["trust_remote_code"] = trust_remote_code

        def _run(text, max_new_tokens):
            calls["ran"] += 1
            return [{"generated_text": "unsafe"}]

        return _run

    fake_module = types.SimpleNamespace(pipeline=fake_pipeline)
    monkeypatch.setitem(sys.modules, "transformers", fake_module)

    judge = HFClassifierJudge(model_id="fake/model", trust_remote_code=True)
    behavior = make_behavior()
    v1 = judge.score(behavior, make_attempt(behavior, "x"))
    v2 = judge.score(behavior, make_attempt(behavior, "y"))

    assert v1.success is True and v2.success is True
    assert calls["built"] == 1  # load-once-per-run
    assert calls["ran"] == 2
    assert calls["model"] == "fake/model"
    assert calls["trust_remote_code"] is True
