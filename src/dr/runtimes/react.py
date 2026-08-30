from __future__ import annotations

from dr.llm import Completion
from dr.types import Action, Observation


class ReActRuntime:
    """Transcript creciente: anade cada observacion, razonamiento y accion."""

    def __init__(self, client, spec: str) -> None:
        self.client = client
        self.spec = spec
        self.history: list[str] = []

    def act(self, observation: Observation) -> tuple[Action | None, list[Completion]]:
        history_block = "\n".join(self.history)
        user = (
            f"History:\n{history_block}\n\n"
            f"Latest Observation: {observation.render()}\n"
            "Generate your next reasoning and action (format 'Action: <cmd>'):"
        )
        completion = self.client.complete(system=f"Instructions:\n{self.spec}", user=user)
        self.history.append(f"Observation: {observation.render()}")
        self.history.append(f"Reasoning & Action: {completion.text}")
        return Action.parse(completion.text), [completion]

    def state_size(self) -> int:
        return 0
