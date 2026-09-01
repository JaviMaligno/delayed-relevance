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
        """Extrae el comando igual para todos los runtimes.

        Si la respuesta trae marcador 'Action:' se lee el ultimo bloque; si no, la
        ultima ocurrencia del texto. El cuerpo JSON se cierra contando llaves, no
        con un regex codicioso: mencionar una accion dentro del razonamiento no
        puede invalidar la respuesta, porque eso penalizaria solo a los brazos que
        razonan en libre.
        """
        if "Action:" in text:
            segment = text.rsplit("Action:", 1)[-1]
            candidates = list(re.finditer(r"([A-Za-z]+)\(\s*(?=\{)", segment))[:1]
        else:
            segment = text
            candidates = list(re.finditer(r"([A-Za-z]+)\(\s*(?=\{)", segment))[-1:]
        for match in candidates:
            body = _balanced_json(segment, match.end())
            if body is None:
                continue
            try:
                args = json.loads(body)
            except json.JSONDecodeError:
                continue
            if not isinstance(args, dict):
                continue
            return cls(name=match.group(1), args=args)
        return None


def _balanced_json(text: str, start: int) -> str | None:
    """Devuelve el objeto JSON que empieza en `start`, cerrando por conteo de llaves."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


@dataclass(frozen=True)
class StepResult:
    step: int
    actionable: bool
    correct: bool
    prompt_tokens: int
    output_tokens: int
    state_size: int = 0
    truncated: int = 0
    cache_read: int = 0
    cache_write: int = 0
