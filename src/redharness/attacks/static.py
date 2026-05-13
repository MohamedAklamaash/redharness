"""Static replay: send the behavior prompt directly, single turn."""

from __future__ import annotations

from redharness.core.attack import Attack
from redharness.core.models import Attempt, Behavior, Message
from redharness.core.registry import register_attack
from redharness.core.target import Target


@register_attack("static")
class StaticReplayAttack(Attack):
    """The baseline attack: replay each behavior prompt verbatim, no jailbreak.

    Establishes the model's unperturbed refusal rate — the control against which
    jailbreak attacks are measured (HarmBench/JBB direct-request baseline).
    """

    name = "static"

    def __init__(self, system_prompt: str | None = None) -> None:
        self.system_prompt = system_prompt

    def run(self, behavior: Behavior, target: Target) -> list[Attempt]:
        messages = []
        if self.system_prompt:
            messages.append(Message(role="system", content=self.system_prompt))
        messages.append(Message(role="user", content=behavior.prompt))
        response = target.generate(messages)
        transcript = [*messages, Message(role="assistant", content=response.text)]
        return [
            Attempt(
                behavior_id=behavior.id,
                attack_name=self.name,
                target_name=target.name,
                transcript=transcript,
                query_count=1,
            )
        ]
