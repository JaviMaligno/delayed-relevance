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
        # La historia va como prefijo cacheable: es append-only, asi que cada paso
        # reenvia el mismo prefijo mas un sufijo nuevo. Es el caso ideal de cache de
        # prefijo, y darsela es lo que hace honesta la comparacion de coste contra un
        # runtime de estado, cuyo bloque muta y no puede cachear.
        # Troceada por turnos: cada bloque es inmutable una vez escrito, que es la
        # condicion para que el cache case en pasos posteriores.
        prefijo = ["History:\n"] + [linea + "\n" for linea in self.history]
        user = (
            f"Latest Observation: {observation.render()}\n"
            "Generate your next reasoning and action (format 'Action: <cmd>'):"
        )
        completion = self.client.complete(
            system=f"Instructions:\n{self.spec}", user=user, cache_prefix=prefijo
        )
        self.history.append(f"Observation: {observation.render()}")
        self.history.append(f"Reasoning & Action: {completion.text}")
        return Action.parse(completion.text), [completion]

    def state_size(self) -> int:
        return 0
