"""Injection scenario suites. Importing this package registers the bundled suite source."""

from redharness.core.registry import register_scenario
from redharness.scenarios.loader import BundledSuite

# Register the bundled-suite source on the scenarios axis; configs select a
# concrete suite via params, e.g. {name: bundled, params: {suite: injecagent_demo}}.
register_scenario("bundled")(BundledSuite)

__all__ = ["BundledSuite"]
