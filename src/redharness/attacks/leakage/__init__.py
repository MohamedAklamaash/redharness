"""Data-leakage probe attacks (plan §5 Phase 3).

These are single-turn probe transformations on the ``Attack`` axis — structurally
identical to the jailbreak attacks (probe -> response -> detect) — so they reuse
the existing jailbreak runner path with no new run mode. Each transforms a leakage
``Behavior`` into a probe designed to elicit a memorized synthetic secret, then the
``leak_detector`` judge checks whether the secret leaked.

Every attack is benign: it ships no real extraction corpus, only the technique. The
docstrings note where a real corpus (e.g. the divergence attack's web-scale prompts,
or a planted-canary training run) would plug in.
"""

from redharness.attacks.leakage.attacks import (
    CanaryCompletionAttack,
    DirectExtractionAttack,
    DivergenceAttack,
    PIIElicitationAttack,
    SystemPromptLeakAttack,
)

__all__ = [
    "CanaryCompletionAttack",
    "DirectExtractionAttack",
    "DivergenceAttack",
    "PIIElicitationAttack",
    "SystemPromptLeakAttack",
]
