"""Target adapters. Importing this package registers the built-in targets."""

from redharness.targets.mock import MockTarget
from redharness.targets.openai_compat import OpenAICompatTarget

__all__ = ["MockTarget", "OpenAICompatTarget"]
