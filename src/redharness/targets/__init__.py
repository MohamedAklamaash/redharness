"""Target adapters. Importing this package registers the built-in targets."""

from redharness.targets.leaky_mock import LeakyMockTarget
from redharness.targets.mock import MockTarget
from redharness.targets.mock_agent import MockAgentTarget
from redharness.targets.openai_compat import OpenAICompatTarget

__all__ = ["LeakyMockTarget", "MockAgentTarget", "MockTarget", "OpenAICompatTarget"]
