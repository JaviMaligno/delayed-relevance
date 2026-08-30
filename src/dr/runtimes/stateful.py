from __future__ import annotations

import json
import re
from typing import Any

from dr.llm import Completion
from dr.runtimes.skillstate import _merge_into
from dr.types import Action, Observation


class StatefulRuntime:
    """Estado estructurado junto al transcript completo (estilo LangGraph)."""

    def __init__(
        self,
        client,
        spec: str,
        schema_fields: list[str],
        deep_merge: bool = True,
    ) -> None:
        self.client = client
        self.spec = spec
        self.schema_fields = schema_fields
        self.deep_merge = deep_merge
        self.state: dict[str, Any] = {}
        self.history: list[str] = []

    def act(self, observation: Observation) -> tuple[Action | None, list[Completion]]:
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
        match = re.search(r"StateUpdate:\s*(\{.*?\})", text, re.DOTALL)
        if match is None:
            return
        try:
            update = json.loads(match.group(1))
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
