from __future__ import annotations

from dataclasses import dataclass, field

import os

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


FOUNDRY_ENV_VARS = (
    "ANTHROPIC_FOUNDRY_API_KEY",
    "ANTHROPIC_FOUNDRY_RESOURCE",
    "ANTHROPIC_FOUNDRY_BASE_URL",
)
AZURE_SCOPE = "https://cognitiveservices.azure.com/.default"


def resolve_provider(requested: str = "auto") -> str:
    """Decide la plataforma. 'auto' usa Foundry si hay cualquier ajuste de Foundry."""
    if requested != "auto":
        return requested
    if any(os.environ.get(name) for name in FOUNDRY_ENV_VARS):
        return "foundry"
    return "api"


def build_foundry_client():
    """Cliente de Foundry, con clave de API si la hay y con Entra ID si no.

    Con `az login` hecho no hace falta ninguna clave: DefaultAzureCredential toma el
    token del CLI. Es la via preferible aqui, porque no deja secretos en disco.
    """
    if os.environ.get("ANTHROPIC_FOUNDRY_API_KEY"):
        return anthropic.AnthropicFoundry()
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    provider = get_bearer_token_provider(DefaultAzureCredential(), AZURE_SCOPE)
    return anthropic.AnthropicFoundry(azure_ad_token_provider=provider)


class AnthropicClient:
    """Cliente real, contra la API de Anthropic o contra Microsoft Foundry.

    Foundry sirve para este experimento porque solo usamos Messages con system y
    user, que esta en GA alli; no tocamos herramientas, thinking ni structured
    outputs, que en Foundry siguen en beta.

    No se envia `temperature`: el SDK `anthropic` 1.x lo ha eliminado de
    `Messages.create()`, asi que no esta disponible para ningun modelo, no solo para
    los de razonamiento. La reproducibilidad del experimento es estadistica —
    seeds, varianza reportada y ruido de muestreo medido aparte — segun spec §8.
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5",
        max_tokens: int = 2048,
        provider: str = "auto",
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.provider = resolve_provider(provider)
        if self.provider == "foundry":
            self._client = build_foundry_client()
        elif self.provider == "api":
            self._client = anthropic.Anthropic()
        else:
            raise ValueError(f"proveedor desconocido: {self.provider}")

    def complete(self, system: str, user: str) -> Completion:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return Completion(
            text=text,
            prompt_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
