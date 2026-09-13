from __future__ import annotations

from dataclasses import dataclass, field

import json
import os
import time
import urllib.error
import urllib.request

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
    thinking_tokens: int = 0
    """Tokens de razonamiento interno, ya sumados dentro de `output_tokens`.

    Se facturan como salida, asi que sumarlos es lo correcto para el coste. Van
    ademas aparte para que un modelo que piensa mucho no se lea como uno que escribe
    mucho. Anthropic no los expone aqui: en este experimento no se pide thinking."""
    model_version: str = ""
    """Modelo que contesta de verdad, tal como lo declara el proveedor.

    Se pide un ID que puede ser un alias o un preview, y el que responde puede no ser
    el que el paper evaluo. Registrarlo es lo que permite declararlo despues."""


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


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_TIMEOUT = 300
GEMINI_RETRY_STATUS = (429, 500, 502, 503, 504)


def post_json(url: str, headers: dict, payload: dict) -> dict:
    """POST de JSON con stdlib. Aislado en una funcion para poder sustituirlo en los
    tests sin tocar la red y sin meter una dependencia nueva solo para hablar REST."""
    body = json.dumps(payload).encode("utf-8")
    peticion = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(peticion, timeout=GEMINI_TIMEOUT) as respuesta:
        return json.loads(respuesta.read())


class GeminiClient:
    """Cliente de la API de Gemini, con la misma firma que `AnthropicClient`.

    Existe por una razon que no es "otro modelo mas": `gemini-3-flash-preview` es el
    modelo de la Tabla 1 del paper y admite `temperature=0`. Con greedy, las seeds
    vuelven a ser instancias del entorno en vez de tiradas del muestreo, que es la
    limitacion mas seria del bloque 1.

    Se habla REST a proposito. El SDK de Google envuelve cualquier respuesta no-2xx
    en un error generico sin status ni cuerpo, y un experimento que no distingue "no
    tengo permiso" de "vuelve luego" miente.

    No implementa cache: la de Gemini es implicita, o explicita con TTL y minimo de
    tokens, no el corte de prefijo de Anthropic. La contabilidad con cache de este
    proveedor es una corrida aparte y se mide, no se extrapola. Lo que si se lee es
    `cachedContentTokenCount`, por si la cache implicita entra sola.
    """

    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        max_tokens: int = 2048,
        temperature: float = 0.0,
        top_p: float = 1.0,
        thinking_budget: int | None = None,
    ) -> None:
        clave = os.environ.get("GEMINI_API_KEY")
        if not clave:
            raise RuntimeError(
                "falta GEMINI_API_KEY: ponla en el entorno o en el .env del repo")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.thinking_budget = thinking_budget
        self.provider = "gemini"
        self._clave = clave

    def complete(self, system: str, user: str, max_tokens: int | None = None,
                 cache_prefix: str | list[str] | None = None) -> Completion:
        """Reintenta cupo y saturacion; no reintenta permiso ni peticion invalida,
        que no se arreglan esperando."""
        espera = 2.0
        for intento in range(RETRY_ATTEMPTS):
            try:
                return self._generate(system, user, max_tokens, cache_prefix)
            except urllib.error.HTTPError as error:
                ultimo = intento == RETRY_ATTEMPTS - 1
                if error.code not in GEMINI_RETRY_STATUS or ultimo:
                    detalle = error.read().decode(errors="replace")[:400]
                    raise RuntimeError(
                        f"HTTP {error.code} de Gemini: {detalle}") from error
                print(f"  [reintento {intento + 1}/{RETRY_ATTEMPTS - 1}] "
                      f"HTTP {error.code}, esperando {espera:.0f}s", flush=True)
            except urllib.error.URLError as error:
                if intento == RETRY_ATTEMPTS - 1:
                    raise
                print(f"  [reintento {intento + 1}/{RETRY_ATTEMPTS - 1}] "
                      f"{type(error).__name__}, esperando {espera:.0f}s", flush=True)
            time.sleep(espera)
            espera = min(espera * 2, 60.0)
        raise RuntimeError("inalcanzable")

    def _generate(self, system: str, user: str, max_tokens: int | None,
                  cache_prefix: str | list[str] | None) -> Completion:
        if isinstance(cache_prefix, list):
            bloques = list(cache_prefix)
        elif cache_prefix:
            bloques = [cache_prefix]
        else:
            bloques = []
        partes = [{"text": bloque} for bloque in bloques] + [{"text": user}]
        config: dict = {
            "temperature": self.temperature,
            "topP": self.top_p,
            "maxOutputTokens": max_tokens or self.max_tokens,
        }
        if self.thinking_budget is not None:
            config["thinkingConfig"] = {"thinkingBudget": self.thinking_budget}
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": partes}],
            "generationConfig": config,
        }
        datos = post_json(
            f"{GEMINI_BASE}/models/{self.model}:generateContent",
            {"content-type": "application/json", "x-goog-api-key": self._clave},
            payload,
        )
        return self._leer(datos)

    @staticmethod
    def _leer(datos: dict) -> Completion:
        """Un bloqueo por filtros devuelve 200 sin `candidates`. Eso no puede tumbar
        una rejilla a medias: se lee como respuesta vacia y truncada, que es lo que
        es, y el episodio queda contado como tal."""
        candidatos = datos.get("candidates") or []
        uso = datos.get("usageMetadata") or {}
        if not candidatos:
            return Completion(
                text="",
                prompt_tokens=uso.get("promptTokenCount", 0),
                output_tokens=0,
                truncated=True,
                model_version=datos.get("modelVersion", ""),
            )
        candidato = candidatos[0]
        partes = (candidato.get("content") or {}).get("parts") or []
        texto = "".join(
            parte.get("text", "") for parte in partes if not parte.get("thought"))
        pensamiento = uso.get("thoughtsTokenCount", 0) or 0
        return Completion(
            text=texto,
            prompt_tokens=uso.get("promptTokenCount", 0),
            output_tokens=(uso.get("candidatesTokenCount", 0) or 0) + pensamiento,
            cache_read=uso.get("cachedContentTokenCount", 0) or 0,
            truncated=candidato.get("finishReason") != "STOP",
            thinking_tokens=pensamiento,
            model_version=datos.get("modelVersion", ""),
        )


def es_desbordamiento_de_contexto(error: Exception) -> bool:
    """Un prompt que no cabe no es un fallo del metodo: es una celda que no se puede
    medir, y hay que contarla como tal en los dos proveedores. Anthropic lo dice con
    una BadRequestError; Gemini, con un 400 que menciona los tokens."""
    mensaje = str(error).lower()
    if "prompt is too long" in mensaje:
        return True
    return "http 400" in mensaje and "token" in mensaje


def build_client(model: str, provider: str = "auto", max_tokens: int = 2048):
    """Un solo punto donde se decide el cliente, para que los corredores no tengan
    que saber de proveedores. El nombre del modelo basta: `gemini-*` va a Gemini y
    todo lo demas a Anthropic, salvo que se fuerce `--provider`."""
    if provider == "gemini" or (provider == "auto" and model.startswith("gemini")):
        return GeminiClient(model=model, max_tokens=max_tokens)
    return AnthropicClient(model=model, provider=provider, max_tokens=max_tokens)
