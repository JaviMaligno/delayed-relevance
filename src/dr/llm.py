from __future__ import annotations

from dataclasses import dataclass, field

import os
import time

import anthropic


@dataclass(frozen=True)
class Completion:
    text: str
    prompt_tokens: int
    output_tokens: int
    cache_read: int = 0
    """Tokens servidos desde cache de prefijo. Cuestan 0.1x."""
    cache_write: int = 0
    """Tokens escritos a cache. Cuestan 1.25x."""
    truncated: bool = False
    """True si la generacion se corto por el tope de salida.

    Importa porque una respuesta truncada parte el bloque JSON del parche y hace que
    SKILL.state falle por el tope, no por el metodo. Sin contarlo, ese artefacto se
    lee como un resultado."""


@dataclass
class FakeClient:
    """Cliente determinista para tests. Cuenta tokens como palabras."""

    responses: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system: str, user: str, max_tokens: int | None = None,
                 cache_prefix: str | list[str] | None = None) -> Completion:
        # El prefijo puede venir troceado en bloques; los tests inspeccionan el prompt
        # completo, asi que se reconstruye tal como lo veria el modelo.
        if isinstance(cache_prefix, list):
            prefijo = "".join(cache_prefix)
        else:
            prefijo = cache_prefix or ""
        self.calls.append((system, prefijo + user))
        text = self.responses.pop(0)
        return Completion(
            text=text,
            prompt_tokens=len((prefijo + user).split()) + len(system.split()),
            output_tokens=len(text.split()),
        )


FOUNDRY_ENV_VARS = (
    "ANTHROPIC_FOUNDRY_API_KEY",
    "ANTHROPIC_FOUNDRY_RESOURCE",
    "ANTHROPIC_FOUNDRY_BASE_URL",
)
RETRY_ATTEMPTS = 6
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
        return anthropic.AnthropicFoundry(max_retries=4)
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    provider = get_bearer_token_provider(DefaultAzureCredential(), AZURE_SCOPE)
    return anthropic.AnthropicFoundry(azure_ad_token_provider=provider, max_retries=4)


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
            self._client = anthropic.Anthropic(max_retries=4)
        else:
            raise ValueError(f"proveedor desconocido: {self.provider}")

    def complete(self, system: str, user: str, max_tokens: int | None = None,
                 cache_prefix: str | list[str] | None = None) -> Completion:
        """Reintenta los fallos transitorios: una rejilla de una hora no puede morir
        por un parpadeo de red. Los errores de autenticacion o de peticion invalida
        NO se reintentan, porque no se arreglan esperando."""
        delay = 2.0
        for attempt in range(RETRY_ATTEMPTS):
            try:
                return self._create(system, user, max_tokens, cache_prefix)
            except (anthropic.APIConnectionError, anthropic.RateLimitError) as error:
                if attempt == RETRY_ATTEMPTS - 1:
                    raise
                print(
                    f"  [reintento {attempt + 1}/{RETRY_ATTEMPTS - 1}] "
                    f"{type(error).__name__}, esperando {delay:.0f}s",
                    flush=True,
                )
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
        raise RuntimeError("inalcanzable")

    def _create(self, system: str, user: str, max_tokens: int | None = None,
                cache_prefix: str | list[str] | None = None) -> Completion:
        """`cache_prefix` es la parte estable del mensaje y lleva el punto de corte de
        cache. Para ReAct es la historia acumulada, que es un prefijo append-only y por
        tanto el caso ideal de cache. Para SKILL.state no hay prefijo estable en el
        mensaje: su bloque de estado muta en cada paso e invalida la cache desde ahi.
        Esa asimetria es justo lo que hay que medir, no algo que corregir."""
        contenido: list[dict] = []
        if cache_prefix:
            # El cache casa por BLOQUES, no por caracteres. Un unico bloque que crece
            # nunca coincide con el del paso anterior, asi que reescribe el prefijo
            # entero cada vez, y escribir cuesta 1.25x: asi el cache ENCARECE en vez
            # de abaratar. La historia se manda troceada en bloques inmutables, con el
            # punto de corte en el ultimo, para que los anteriores si casen.
            bloques = cache_prefix if isinstance(cache_prefix, list) else [cache_prefix]
            for indice, bloque in enumerate(bloques):
                entrada: dict = {"type": "text", "text": bloque}
                if indice == len(bloques) - 1:
                    entrada["cache_control"] = {"type": "ephemeral"}
                contenido.append(entrada)
        contenido.append({"type": "text", "text": user})
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": contenido}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return Completion(
            text=text,
            prompt_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            cache_write=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
            truncated=response.stop_reason == "max_tokens",
        )
