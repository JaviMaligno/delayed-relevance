from __future__ import annotations

from dataclasses import dataclass, field

import anthropic


@dataclass(frozen=True)
class Completion:
    text: str
    prompt_tokens: int
    output_tokens: int


@dataclass
class FakeClient:
    """Cliente determinista para tests. Cuenta tokens como palabras."""

    responses: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system: str, user: str) -> Completion:
        self.calls.append((system, user))
        text = self.responses.pop(0)
        return Completion(
            text=text,
            prompt_tokens=len(system.split()) + len(user.split()),
            output_tokens=len(text.split()),
        )


class AnthropicClient:
    """Cliente real. Temperatura 0 para reproducibilidad; solo valido en Haiku 4.5."""

    def __init__(self, model: str = "claude-haiku-4-5", max_tokens: int = 2048) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic()

    def complete(self, system: str, user: str) -> Completion:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return Completion(
            text=text,
            prompt_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
