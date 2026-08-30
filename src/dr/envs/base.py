from __future__ import annotations

from typing import Protocol, runtime_checkable

from dr.types import Action, Observation


@runtime_checkable
class Environment(Protocol):
    """Un entorno genera observaciones y sabe cual era la accion correcta.

    No sabe nada de LLMs ni de runtimes: solo de su propio dominio.
    """

    def reset(self) -> Observation:
        """Estado inicial. Devuelve la primera observacion."""

    def observe(self) -> Observation:
        """Observacion del paso actual, sin avanzar."""

    def expected_action(self) -> Action:
        """Accion correcta para la observacion actual, segun el estado verdadero."""

    def apply(self, action: Action) -> None:
        """Aplica la accion del agente y avanza un paso."""

    @property
    def done(self) -> bool:
        """True cuando se agoto el horizonte."""

    def spec(self) -> str:
        """Especificacion procedimental inmutable P que se pasa al modelo."""

    def schema_fields(self) -> list[str]:
        """Campos del esquema de estado para los runtimes que lo usen."""
