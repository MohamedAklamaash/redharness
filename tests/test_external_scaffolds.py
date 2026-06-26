"""The external-attack scaffolds (GCG / garak / PyRIT) must fail loudly, not silently.

Each is a registered seam whose heavy dependency (torch / garak / pyrit) is unverified
in CI. Invoking ``run`` without the extra installed must raise a typed
:class:`ExternalAttackUnavailable` that names the extra — never a bare ``ImportError``,
and never a bogus ``Attempt``. The missing extra is simulated by blanking the heavy
module in ``sys.modules`` (mirrors the live-adapter "extra not installed" tests), so
the test is deterministic whether or not torch/garak/pyrit happen to be installed.
"""

from __future__ import annotations

import sys

import pytest

from redharness.attacks.external.garak_adapter import GarakAttack
from redharness.attacks.external.gcg import GCGAttack
from redharness.attacks.external.pyrit_adapter import PyRITAttack
from redharness.core.registry import registry
from redharness.errors import ExternalAttackUnavailable
from tests.conftest import make_behavior

SCAFFOLDS = [
    (GCGAttack, "gcg", "torch"),
    (GarakAttack, "garak", "garak"),
    (PyRITAttack, "pyrit", "pyrit"),
]


@pytest.mark.parametrize(("cls", "extra", "import_name"), SCAFFOLDS)
def test_scaffold_without_extra_raises_typed_error(monkeypatch, cls, extra, import_name):
    monkeypatch.setitem(sys.modules, import_name, None)  # simulate the extra absent
    attack = cls()
    with pytest.raises(ExternalAttackUnavailable) as exc:
        attack.run(make_behavior(), target=None)  # type: ignore[arg-type]
    message = str(exc.value)
    assert extra in message  # the helpful message names the pip extra
    assert "scaffold" in message  # and flags it as unverified in CI


@pytest.mark.parametrize(("cls", "extra", "import_name"), SCAFFOLDS)
def test_scaffold_is_registered_by_name(cls, extra, import_name):
    assert registry.attacks.get(extra) is cls
    assert cls.extra == extra
    assert cls.import_name == import_name
