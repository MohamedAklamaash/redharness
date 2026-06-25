"""Target adapters. Importing this package registers the built-in targets."""

from redharness.targets.openai_compat import OpenAICompatTarget
from redharness.targets.reference import ReferenceTarget
from redharness.targets.reference_agent import ReferenceAgent
from redharness.targets.reference_memorizer import ReferenceMemorizer

__all__ = [
    "OpenAICompatTarget",
    "ReferenceAgent",
    "ReferenceMemorizer",
    "ReferenceTarget",
]
