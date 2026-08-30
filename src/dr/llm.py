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


TEMPERATURE_ZERO_MODELS = ("claude-haiku-4-5",)
_AUTO = object()


class AnthropicClient:
    """Cliente real.

    Temperatura 0 solo donde esta disponible (Haiku 4.5). En modelos de razonamiento
    no lo esta, y el spec declara que Sonnet 5 corre con su muestreo por defecto, asi
    que el parametro se omite del todo en vez de enviarse.
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5",
        max_tokens: int = 2048,
        temperature: float | None | object = _AUTO,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        if temperature is _AUTO:
            temperature = 0 if model.startswith(TEMPERATURE_ZERO_MODELS) else None
        self.temperature: float | None = temperature  # type: ignore[assignment]
        self._client = anthropic.Anthropic()

    def complete(self, system: str, user: str) -> Completion:
        kwargs: dict = {}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            **kwargs,
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return Completion(
            text=text,
            prompt_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
