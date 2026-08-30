from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Observation:
    step: int
    text: str
    actionable: bool

    def render(self) -> str:
        return f"[step {self.step}] {self.text}"


@dataclass(frozen=True)
class Action:
    name: str
    args: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        return f"{self.name}({json.dumps(self.args, sort_keys=True)})"

    @classmethod
    def parse(cls, text: str) -> Action | None:
        match = re.search(r"([A-Za-z]+)\((\{.*\})\)", text, re.DOTALL)
        if match is None:
            return None
        try:
            args = json.loads(match.group(2))
        except json.JSONDecodeError:
            return None
        if not isinstance(args, dict):
            return None
        return cls(name=match.group(1), args=args)


@dataclass(frozen=True)
class StepResult:
    step: int
    actionable: bool
    correct: bool
    prompt_tokens: int
    output_tokens: int
    state_size: int = 0
