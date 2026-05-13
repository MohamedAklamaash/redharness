"""Attack plugins. Importing this package registers the offline attacks."""

from redharness.attacks.static import StaticReplayAttack
from redharness.attacks.template import TemplateJailbreakAttack

__all__ = ["StaticReplayAttack", "TemplateJailbreakAttack"]
