"""ABC for external attack-framework adapters (no heavy deps in the core).

Two kinds of adapter live here. **Implemented** adapters (PAIR, TAP, Crescendo) are
pure-Python orchestration over injected providers and are fully offline-testable.
**Scaffolds** (GCG, garak, PyRIT) are registered seams whose heavy dependency
(``torch`` / ``garak`` / ``pyrit``) is unverified in CI: they import that dependency
lazily inside :meth:`run` and raise a typed :class:`ExternalAttackUnavailable`
naming the optional extra, never importing anything heavy at module load (which
would break ``import redharness`` for everyone, since ``plugins.py`` eagerly imports
every plugin submodule). Promote a scaffold to an implemented adapter by replacing
its :meth:`ScaffoldAttack.run` with a real, tested translation to ``Attempt``s.
"""

from __future__ import annotations

import importlib
from abc import abstractmethod

from redharness.core.attack import Attack
from redharness.core.models import Attempt, Behavior
from redharness.core.target import Target
from redharness.errors import ExternalAttackUnavailable


class ExternalAttack(Attack):
    """Wraps a third-party attack framework behind the ``Attack`` interface.

    Concrete adapters import their framework lazily inside :meth:`run`, declare the
    extra dependency group needed to use them, and convert the framework's run into
    ``Attempt`` objects. They are not part of the offline slice.
    """

    #: pip extra that must be installed for this adapter, e.g. ``"pair"``.
    extra: str = ""

    @abstractmethod
    def run(self, behavior: Behavior, target: Target) -> list[Attempt]:  # pragma: no cover
        raise NotImplementedError


class ScaffoldAttack(ExternalAttack):
    """A registered-but-unimplemented external attack behind an optional extra.

    Subclasses set :attr:`name`, :attr:`extra`, and :attr:`import_name` (the heavy
    module to probe). :meth:`run` lazily attempts that import and raises a typed,
    helpful :class:`ExternalAttackUnavailable` when the extra is missing — and, when
    the extra *is* present, still raises (the scaffold is unverified in CI) so it can
    never silently produce bogus results.
    """

    #: The heavy module a real implementation would need (e.g. ``"torch"``).
    import_name: str = ""

    def _require(self) -> None:
        try:
            importlib.import_module(self.import_name)
        except ImportError as exc:
            raise ExternalAttackUnavailable(
                f"the {self.name!r} attack is an unverified-in-CI scaffold requiring "
                f"the {self.extra!r} extra (module {self.import_name!r}); install it "
                f"with `pip install 'redharness[{self.extra}]'` and implement "
                f"{type(self).__name__}.run before use"
            ) from exc

    def run(self, behavior: Behavior, target: Target) -> list[Attempt]:
        self._require()
        raise ExternalAttackUnavailable(  # pragma: no cover - requires the heavy extra
            f"the {self.name!r} attack is a registered scaffold that is not "
            f"implemented or verified in CI; implement {type(self).__name__}.run "
            "before use"
        )
