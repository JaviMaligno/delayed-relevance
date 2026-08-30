from __future__ import annotations

import json
import re
from typing import Any

from dr.llm import Completion
from dr.types import Action, Observation

MAX_RETRIES = 2


def _merge_into(target: dict[str, Any], patch: dict[str, Any], deep: bool) -> None:
    """Aplica un parche con semantica de borrado por null.

    `deep=True` desciende en los diccionarios anidados, de modo que tocar una clave
    interna no destruye a sus hermanas. Con `deep=False` el merge es de primer nivel
    y reemplaza el valor entero: sobre un esquema anidado eso fabrica el modo de
    fallo de "borrado prematuro" sin que el modelo se equivoque, porque emitir solo
    la sub-clave modificada es la lectura natural de "tus actualizaciones de estado".

    Se conservan las dos variantes a proposito: la sensibilidad del metodo a la
    profundidad del merge es un resultado, no un detalle de implementacion.
    """
    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        elif deep and isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_into(target[key], value, deep=True)
        else:
            target[key] = value


class SkillStateRuntime:
    """(P, Sigma_t, O_t). El razonamiento se descarta tras validar el parche."""

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
        self.invalid_patches = 0

    def _merge_doc(self) -> str:
        if self.deep_merge:
            return (
                "your patch is merged key by key, descending into nested objects, so "
                "you may send only the sub-keys that changed. Set a key to null to delete it."
            )
        return (
            "your patch replaces each top-level key outright, so any nested object you "
            "send must be COMPLETE - omitted sub-keys are lost. Set a key to null to delete it."
        )

    def _prompt(self, observation: Observation) -> str:
        return (
            "Skill Execution State:\n"
            f"```json\n{json.dumps(self.state, separators=(',', ':'))}\n```\n"
            f"State schema (only these keys are valid): {', '.join(self.schema_fields)}\n"
            f"Patch semantics: {self._merge_doc()}\n"
            f"Latest Observation: {observation.render()}\n\n"
            "Provide your response with:\n"
            "1. Step-by-step reasoning (will be discarded after execution)\n"
            "2. A JSON block fenced with ```json ... ``` containing both your State Patch "
            'and your Action. The JSON block MUST have exactly these two keys: '
            '{ "state_patch": { <dict: your state updates, set keys to null to delete> }, '
            '"action": "<string: the exact command you want to execute>" }'
        )

    def act(self, observation: Observation) -> tuple[Action | None, list[Completion]]:
        completions: list[Completion] = []
        for _ in range(MAX_RETRIES + 1):
            completion = self.client.complete(
                system=f"Instructions:\n{self.spec}", user=self._prompt(observation)
            )
            completions.append(completion)
            parsed = self._parse(completion.text)
            if parsed is not None and self._within_schema(parsed[0]):
                patch, action_text = parsed
                self._merge(patch)
                return Action.parse(action_text), completions
            self.invalid_patches += 1
        return None, completions

    @staticmethod
    def _parse(text: str) -> tuple[dict[str, Any], str] | None:
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match is None:
            return None
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        patch = payload.get("state_patch")
        action = payload.get("action")
        if not isinstance(patch, dict) or not isinstance(action, str):
            return None
        return patch, action

    def _within_schema(self, patch: dict[str, Any]) -> bool:
        """Un parche con claves fuera del esquema es invalido: Sigma no es de campos libres."""
        return all(key in self.schema_fields for key in patch)

    def _merge(self, patch: dict[str, Any]) -> None:
        _merge_into(self.state, patch, deep=self.deep_merge)

    def state_size(self) -> int:
        return len(json.dumps(self.state))
