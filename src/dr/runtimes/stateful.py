from __future__ import annotations

import json
import re
from typing import Any

from dr.llm import Completion
from dr.runtimes.skillstate import _merge_into
from dr.types import Action, Observation


PARSER_VERSION = 3
"""1: regex no codiciosa, tiraba todo parche anidado. 2: raw_decode, pero exigia la
llave justo tras `StateUpdate:` y tiraba los parches en Markdown. 3: tolera negritas y
bloques de codigo entre la etiqueta y el objeto. Va en la cabecera de cada traza para
que ningun agregado mezcle versiones."""


class StatefulRuntime:
    """Estado estructurado junto al transcript completo (estilo LangGraph)."""

    def __init__(
        self,
        client,
        spec: str,
        schema_fields: list[str],
        deep_merge: bool = True,
        orden: str = "estado_primero",
        cachear: bool = False,
    ) -> None:
        """`orden` y `cachear` existen para aislar el efecto del orden del prompt en el
        coste: con los dos ordenes marcando cache, lo unico que cambia es que va primero.
        Los valores por defecto reproducen exactamente el runtime ya medido."""
        if orden not in ("estado_primero", "historia_primero"):
            raise ValueError(f"orden desconocido: {orden}")
        self.orden = orden
        self.cachear = cachear
        self.client = client
        self.spec = spec
        self.schema_fields = schema_fields
        self.deep_merge = deep_merge
        self.state: dict[str, Any] = {}
        self.history: list[str] = []

    def act(self, observation: Observation) -> tuple[Action | None, list[Completion]]:
        if self.cachear:
            return self._act_con_cache(observation)
        history_block = "\n".join(self.history)
        user = (
            f"Current State:\n{json.dumps(self.state, indent=2)}\n"
            f"State schema (only these keys are valid): {', '.join(self.schema_fields)}\n\n"
            f"History:\n{history_block}\n\n"
            f"Latest Observation: {observation.render()}\n"
            "Update the state if necessary, provide reasoning, and output 'Action: <cmd>'.\n"
            'To update state, use the format: StateUpdate: {"key": "value"}\n'
            f"Patch semantics: {self._merge_doc()}"
        )
        completion = self.client.complete(system=f"Instructions:\n{self.spec}", user=user)
        self._apply_state_update(completion.text)
        self.history.append(f"Observation: {observation.render()}")
        self.history.append(f"Response: {completion.text}")
        return Action.parse(completion.text), [completion]

    def _cola(self, observation: Observation) -> str:
        return (
            f"Latest Observation: {observation.render()}\n"
            "Update the state if necessary, provide reasoning, and output 'Action: <cmd>'.\n"
            'To update state, use the format: StateUpdate: {"key": "value"}\n'
            f"Patch semantics: {self._merge_doc()}"
        )

    def _act_con_cache(self, observation: Observation) -> tuple[Action | None, list[Completion]]:
        """Mismo contenido que `act`, con la historia en bloques inmutables marcados como
        prefijo cacheable. Con `estado_primero` el bloque de estado encabeza el prefijo y
        muta en cada paso; con `historia_primero` va detras, fuera del prefijo."""
        estado = (f"Current State:\n{json.dumps(self.state, indent=2)}\n"
                  f"State schema (only these keys are valid): {', '.join(self.schema_fields)}\n\n")
        historia = ["History:\n"] + [linea + "\n" for linea in self.history]
        if self.orden == "historia_primero":
            prefijo, user = historia, "\n" + estado + self._cola(observation)
        else:
            prefijo, user = [estado] + historia, "\n" + self._cola(observation)
        completion = self.client.complete(system=f"Instructions:\n{self.spec}", user=user,
                                          cache_prefix=prefijo)
        self._apply_state_update(completion.text)
        self.history.append(f"Observation: {observation.render()}")
        self.history.append(f"Response: {completion.text}")
        return Action.parse(completion.text), [completion]

    def _merge_doc(self) -> str:
        if self.deep_merge:
            return (
                "your update is merged key by key, descending into nested objects, so "
                "you may send only the sub-keys that changed."
            )
        return (
            "your update replaces each top-level key outright, so any nested object you "
            "send must be COMPLETE - omitted sub-keys are lost."
        )

    def _apply_state_update(self, text: str) -> None:
        # Se lee UN objeto JSON completo con raw_decode. La regex no codiciosa de antes
        # cortaba en la primera llave de cierre, asi que todo parche anidado -- el caso
        # normal en shelf_contents -- se tiraba en silencio: 0 de 6.000 aplicados en R2.
        # v3: entre la etiqueta y la llave puede haber dos puntos, negritas y un bloque
        # de codigo (`**StateUpdate:**` + ```json), que es como lo escribe Haiku.
        match = re.search(r"StateUpdate[\s*:]*(?:```(?:json)?[ \t]*\n?)?\s*(?=\{)", text)
        if match is None:
            return
        try:
            update, _ = json.JSONDecoder().raw_decode(text, match.end())
        except json.JSONDecodeError:
            return
        if isinstance(update, dict):
            # Mismo esquema fijo que el brazo de estado. Este runtime no tiene bucle de
            # validacion, asi que las claves ajenas se descartan en vez de reintentarse.
            allowed = {k: v for k, v in update.items() if k in self.schema_fields}
            # Misma profundidad de merge que SKILL.state: si un brazo conserva las
            # sub-claves hermanas y el otro no, la comparacion queda sesgada.
            _merge_into(self.state, allowed, deep=self.deep_merge)

    def state_size(self) -> int:
        return len(json.dumps(self.state))
