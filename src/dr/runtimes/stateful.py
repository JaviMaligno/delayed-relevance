from __future__ import annotations

import json
import re
from typing import Any

from dr.llm import Completion
from dr.types import Action, Observation


class StatefulRuntime:
    """Estado estructurado junto al transcript completo (estilo LangGraph)."""

    def __init__(self, client, spec: str, schema_fields: list[str]) -> None:
        self.client = client
        self.spec = spec
        self.schema_fields = schema_fields
        self.state: dict[str, Any] = {}
        self.history: list[str] = []

    def act(self, observation: Observation) -> tuple[Action | None, list[Completion]]:
        history_block = "\n".join(self.history)
        user = (
            f"Current State:\n{json.dumps(self.state, indent=2)}\n\n"
            f"History:\n{history_block}\n\n"
            f"Latest Observation: {observation.render()}\n"
            "Update the state if necessary, provide reasoning, and output 'Action: <cmd>'.\n"
            'To update state, use the format: StateUpdate: {"key": "value"}'
        )
        completion = self.client.complete(system=f"Instructions:\n{self.spec}", user=user)
        self._apply_state_update(completion.text)
        self.history.append(f"Observation: {observation.render()}")
        self.history.append(f"Response: {completion.text}")
        return Action.parse(completion.text), [completion]

    def _apply_state_update(self, text: str) -> None:
        match = re.search(r"StateUpdate:\s*(\{.*?\})", text, re.DOTALL)
        if match is None:
            return
        try:
            update = json.loads(match.group(1))
        except json.JSONDecodeError:
            return
        if isinstance(update, dict):
            self.state.update(update)

    def state_size(self) -> int:
        return len(json.dumps(self.state))
