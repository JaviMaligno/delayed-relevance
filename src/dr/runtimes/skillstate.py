from __future__ import annotations

import json
import re
from typing import Any

from dr.llm import Completion
from dr.types import Action, Observation

MAX_RETRIES = 2


class SkillStateRuntime:
    """(P, Sigma_t, O_t). El razonamiento se descarta tras validar el parche."""

    def __init__(self, client, spec: str, schema_fields: list[str]) -> None:
        self.client = client
        self.spec = spec
        self.schema_fields = schema_fields
        self.state: dict[str, Any] = {}
        self.invalid_patches = 0

    def _prompt(self, observation: Observation) -> str:
        return (
            "Skill Execution State:\n"
            f"```json\n{json.dumps(self.state, separators=(',', ':'))}\n```\n"
            f"Latest Observation: {observation.render()}\n\n"
            "Provide your response with:\n"
            "1. Step-by-step reasoning (will be discarded after execution)\n"
            "2. A JSON block fenced with ```json ... ``` containing both your State Patch "
            'and your Action. The JSON block MUST have exactly these two keys: '
            '{ "state_patch": { <dict: your state updates, set keys to null to delete> }, '
            '"action": "<string: the exact command you want to execute>" }'
        )

    def act(self, observation: Observation) -> tuple[Action | None, Completion]:
        completion = None
        for _ in range(MAX_RETRIES + 1):
            completion = self.client.complete(
                system=f"Instructions:\n{self.spec}", user=self._prompt(observation)
            )
            parsed = self._parse(completion.text)
            if parsed is not None:
                patch, action_text = parsed
                self._merge(patch)
                return Action.parse(action_text), completion
            self.invalid_patches += 1
        return None, completion

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

    def _merge(self, patch: dict[str, Any]) -> None:
        for key, value in patch.items():
            if value is None:
                self.state.pop(key, None)
            else:
                self.state[key] = value

    def state_size(self) -> int:
        return len(json.dumps(self.state))
