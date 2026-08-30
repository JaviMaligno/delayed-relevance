from __future__ import annotations

from typing import Protocol, runtime_checkable

from dr.llm import Completion
from dr.types import Action, Observation


@runtime_checkable
class Runtime(Protocol):
    """Un runtime decide que contexto ve el modelo en cada paso.

    No sabe nada del dominio: recibe observaciones y devuelve acciones.
    """

    def act(self, observation: Observation) -> tuple[Action | None, Completion]:
        """Consulta al modelo y devuelve la accion elegida y el consumo del paso."""

    def state_size(self) -> int:
        """Tamano del estado explicito en caracteres. Cero si el runtime no tiene."""
