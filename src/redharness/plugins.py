"""Import the built-in plugin packages so the registries are populated.

Plugins register themselves as a side effect of import (decorators run at module
load). Anything that needs a fully populated registry — the CLI, the runner —
imports this module first.
"""

from __future__ import annotations

import redharness.attacks
import redharness.datasets
import redharness.judges
import redharness.metrics
import redharness.scenarios
import redharness.targets  # noqa: F401
