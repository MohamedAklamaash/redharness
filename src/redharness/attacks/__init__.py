"""Attack plugins. Importing this package registers the offline attacks.

Importing the ``injection`` subpackage registers the direct/indirect injection
attacks (and the no-injection baseline) on the ``injections`` axis.
"""

import redharness.attacks.injection  # noqa: F401  (register injection attacks)
from redharness.attacks.static import StaticReplayAttack
from redharness.attacks.template import TemplateJailbreakAttack

__all__ = ["StaticReplayAttack", "TemplateJailbreakAttack"]
