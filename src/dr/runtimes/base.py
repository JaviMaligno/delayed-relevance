from __future__ import annotations

from typing import Protocol, runtime_checkable

from dr.llm import Completion
from dr.types import Action, Observation


@runtime_checkable
class Runtime(Protocol):
    """Un runtime decide que contexto ve el modelo en cada paso.

    No sabe nada del dominio: recibe observaciones y devuelve acciones.
    """

    def act(self, observation: Observation) -> tuple[Action | None, list[Completion]]:
        """Consulta al modelo y devuelve la accion elegida y TODAS las completions del paso.

        La lista incluye las llamadas auxiliares (resumenes, reintentos): el coste es
        una metrica del estudio, no puede quedarse fuera de la contabilidad.
        """

    def state_size(self) -> int:
        """Tamano del estado explicito en caracteres. Cero si el runtime no tiene."""
