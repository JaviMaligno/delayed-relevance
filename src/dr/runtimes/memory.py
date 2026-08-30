from __future__ import annotations

from dr.llm import Completion
from dr.types import Action, Observation

WINDOW = 3


class MemoryRuntime:
    """Resumen acumulado en lenguaje natural mas una ventana de 3 pasos."""

    def __init__(self, client, spec: str) -> None:
        self.client = client
        self.spec = spec
        self.summary = "(empty)"
        self.recent: list[str] = []

    def act(self, observation: Observation) -> tuple[Action | None, Completion]:
        recent_block = "\n".join(self.recent[-WINDOW * 2 :])
        user = (
            f"Summarized History:\n{self.summary}\n\n"
            f"Recent History:\n{recent_block}\n\n"
            f"Latest Observation: {observation.render()}\n"
            "Generate your next reasoning and action (format 'Action: <cmd>'):"
        )
        completion = self.client.complete(system=f"Instructions:\n{self.spec}", user=user)
        self.recent.append(f"Observation: {observation.render()}")
        self.recent.append(f"Response: {completion.text}")
        self._refresh_summary()
        return Action.parse(completion.text), completion

    def _refresh_summary(self) -> None:
        dropped = self.recent[: -WINDOW * 2]
        if not dropped:
            return
        summary_completion = self.client.complete(
            system="Summarise the warehouse execution so far. Be terse and factual.",
            user=f"Previous summary:\n{self.summary}\n\nNewly dropped turns:\n" + "\n".join(dropped),
        )
        self.summary = summary_completion.text
        self.recent = self.recent[-WINDOW * 2 :]

    def state_size(self) -> int:
        return 0
