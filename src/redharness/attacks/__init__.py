"""Attack plugins. Importing this package registers the offline attacks.

Importing the ``injection`` subpackage registers the direct/indirect injection
attacks (and the no-injection baseline) on the ``injections`` axis. Importing the
``leakage`` subpackage registers the data-leakage probe attacks on the (shared)
``attacks`` axis — they reuse the single-turn jailbreak runner path.
"""

import redharness.attacks.external  # register the PAIR external attack
import redharness.attacks.injection
import redharness.attacks.leakage  # noqa: F401  (register leakage probe attacks)
from redharness.attacks.static import StaticReplayAttack
from redharness.attacks.template import TemplateJailbreakAttack

__all__ = ["StaticReplayAttack", "TemplateJailbreakAttack"]
