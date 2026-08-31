from __future__ import annotations

from dr.llm import Completion
from dr.types import Action, Observation

WINDOW = 3
SUMMARY_MAX_TOKENS = 1200
"""El resumen NO hereda el limite de brevedad de la especificacion.

Aquel rige las respuestas de decision, donde escribir largo hace que la accion se
corte. Aqui el objetivo es el contrario: no perder informacion. Con el tope de
decision (600) los resumenes se cortaban a media frase, y un resumen corrupto
penaliza a este baseline por un parametro del corredor, no por su metodo. El prompt
de Memory del paper ronda los 6.400 tokens a T=25, asi que sus resumenes tampoco
son cortos."""


class MemoryRuntime:
    """Resumen acumulado en lenguaje natural mas una ventana de 3 pasos."""

    def __init__(self, client, spec: str) -> None:
        self.client = client
        self.spec = spec
        self.summary = "(empty)"
        self.recent: list[str] = []

    def act(self, observation: Observation) -> tuple[Action | None, list[Completion]]:
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
        completions = [completion, *self._refresh_summary()]
        return Action.parse(completion.text), completions

    def _refresh_summary(self) -> list[Completion]:
        """Devuelve las completions gastadas en resumir, para que el runner las sume."""
        dropped = self.recent[: -WINDOW * 2]
        if not dropped:
            return []
        summary_completion = self.client.complete(
            # Sin nombrar el dominio: el runtime no lo conoce, y los proximos entornos
            # (Software Repository, tau-Bench) no son un almacen.
            system=(
                "Summarise the execution so far for an operator who must keep acting and "
                "will no longer see the raw history. Preserve every fact that a later "
                "decision could depend on, especially the current value of anything you "
                "or the environment changed, and anything that was undone. Drop "
                "decorative metadata. Be factual, not narrative. "
                "Stay under 400 words so your summary is never cut off."
            ),
            user=f"Previous summary:\n{self.summary}\n\nNewly dropped turns:\n" + "\n".join(dropped),
            max_tokens=SUMMARY_MAX_TOKENS,
        )
        self.summary = summary_completion.text
        self.recent = self.recent[-WINDOW * 2 :]
        return [summary_completion]

    def state_size(self) -> int:
        return 0
