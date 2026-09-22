from __future__ import annotations

from dataclasses import dataclass, field

import json
import os
import subprocess
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


AZURE_TOKEN_TTL = 45 * 60
"""Cuanto se reutiliza el token de Foundry antes de volver a invocar `az`.

El token dura una hora larga; esto deja margen y evita que ocho episodios en paralelo
conviertan cada peticion en una invocacion del CLI."""
AZURE_REINTENTOS = 6

_token_azure: tuple[str, float] | None = None


def _az(*args: str) -> str:
    salida = subprocess.run(("az", *args), capture_output=True, text=True)
    if salida.returncode != 0:
        raise RuntimeError(f"az {' '.join(args)} fallo: {salida.stderr.strip()[:200]}")
    return salida.stdout.strip()


def olvidar_token_azure() -> None:
    """Tira la cache. Existe para que los tests no se contaminen entre si."""
    global _token_azure
    _token_azure = None


def _es_caducidad_de_azure(error: Exception) -> bool:
    """La sesion de `az` caducada, que no se arregla sola y si se arregla si alguien
    corre `az login`. Se distingue de un CLI que no responde a tiempo, que si mejora
    reintentando, y de cualquier otro fallo, que no mejora esperando."""
    mensaje = str(error).lower()
    return "az login" in mensaje or "refresh token has expired" in mensaje


def azure_access_token() -> str:
    """Token de Entra ID para Foundry, pedido al CLI y guardado mientras dure.

    Sustituye a `DefaultAzureCredential`, que recorria toda su cadena --con una sonda
    de red a IMDS-- en cada proceso: con ocho episodios en paralelo, `az` dejaba de
    responder a tiempo y la tanda perdia episodios con la sesion viva.

    Ante una caducidad **espera** en vez de morir, igual que la tanda de Vertex: la
    sesion se renueva con `az login` en otra terminal y el episodio sigue por donde
    iba."""
    global _token_azure
    if _token_azure and time.time() < _token_azure[1]:
        return _token_azure[0]
    espera = 2.0
    esperado = 0.0
    intento = 0
    while True:
        try:
            token = _az("account", "get-access-token", "--scope", AZURE_SCOPE,
                        "--query", "accessToken", "-o", "tsv")
        except RuntimeError as error:
            if _es_caducidad_de_azure(error):
                if esperado >= ESPERA_MAXIMA_SESION:
                    raise
                print(f"  [sesion de az caducada] esperando a `az login` "
                      f"({esperado / 60:.0f} min de {ESPERA_MAXIMA_SESION // 60})",
                      flush=True)
                time.sleep(ESPERA_ENTRE_AVISOS)
                esperado += ESPERA_ENTRE_AVISOS
                continue
            intento += 1
            if intento >= AZURE_REINTENTOS:
                raise
            print(f"  [token de azure] reintento {intento}/{AZURE_REINTENTOS - 1}, "
                  f"esperando {espera:.0f}s", flush=True)
            time.sleep(espera)
            espera = min(espera * 2, 30.0)
        else:
            _token_azure = (token, time.time() + AZURE_TOKEN_TTL)
            return token


def build_foundry_client():
    """Cliente de Foundry, con clave de API si la hay y con Entra ID si no.

    Con `az login` hecho no hace falta ninguna clave: el token sale del CLI. Es la via
    preferible aqui, porque no deja secretos en disco.
    """
    if os.environ.get("ANTHROPIC_FOUNDRY_API_KEY"):
        return anthropic.AnthropicFoundry(max_retries=4)
    return anthropic.AnthropicFoundry(azure_ad_token_provider=azure_access_token,
                                      max_retries=4)


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

VERTEX_HOST = "aiplatform.googleapis.com"
VERTEX_TOKEN_TTL = 45 * 60
"""Segundos que se reutiliza un token de gcloud antes de pedir otro.

Viven una hora y R1 dura mas: sin renovarlo, la rejilla se cae a media celda con un
401 que no se arregla esperando, asi que el reintento no lo salvaria."""


def _gcloud(*args: str) -> str:
    salida = subprocess.run(("gcloud", *args), capture_output=True, text=True)
    if salida.returncode != 0:
        raise RuntimeError(
            f"gcloud {' '.join(args)} fallo: {salida.stderr.strip()[:200]}")
    return salida.stdout.strip()


ESPERA_MAXIMA_SESION = 3 * 60 * 60
"""Cuanto se espera, como mucho, a que alguien renueve la sesion de gcloud.

Esperar para siempre es peor que fallar: la tanda parece viva y no lo esta."""
ESPERA_ENTRE_AVISOS = 60


def _es_caducidad_de_sesion(error: Exception) -> bool:
    """La credencial SSO caducada, que NO se arregla sola y SI se arregla si alguien
    corre `gcloud auth login`. Se distingue de cualquier otro fallo de gcloud -- un
    binario que no esta, un proyecto mal puesto -- que no mejora esperando."""
    mensaje = str(error).lower()
    return "reauthentication" in mensaje or "reauth" in mensaje


def gcloud_access_token() -> str:
    """Token de las credenciales por defecto del CLI.

    Es el equivalente de lo que Foundry hace con `az login`: con la sesion de gcloud
    hecha no hace falta ninguna clave, y no queda ningun secreto en disco ni en el
    entorno del proceso.

    Si la sesion ha caducado, **espera** en vez de morir. La credencial SSO dura unas
    horas y una rejilla dura mas; hoy se han perdido cuatro tandas por eso, una de 50
    episodios. Con esto, la tanda se queda parada avisando por consola y continua por
    donde iba en cuanto alguien corre `gcloud auth login` en otra terminal. Lo que
    arreglaria esto de raiz es Workload Identity Federation (`docs/wif-actions.md`),
    cuya alta esta bloqueada por permisos de IAM."""
    esperado = 0.0
    while True:
        try:
            return _gcloud("auth", "print-access-token")
        except RuntimeError as error:
            if not _es_caducidad_de_sesion(error) or esperado >= ESPERA_MAXIMA_SESION:
                raise
            print(f"  [sesion caducada] esperando a `gcloud auth login` "
                  f"({esperado / 60:.0f} min de {ESPERA_MAXIMA_SESION // 60})",
                  flush=True)
            time.sleep(ESPERA_ENTRE_AVISOS)
            esperado += ESPERA_ENTRE_AVISOS


def gcloud_project() -> str:
    """Proyecto activo del CLI, o cadena vacia si no hay ninguno configurado."""
    try:
        return _gcloud("config", "get-value", "project")
    except RuntimeError:
        return ""



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
        backend: str = "api",
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.thinking_budget = thinking_budget
        self.backend = backend
        self._clave = ""
        self._token = ""
        self._token_pedido = 0.0
        if backend == "vertex":
            # El proveedor se declara distinto a proposito: su nombre entra en el
            # fichero de checkpoint, y episodios de dos backends en un mismo fichero
            # serian celdas de procedencia desconocida.
            self.provider = "vertex"
            self.location = os.environ.get("GEMINI_VERTEX_LOCATION", "global")
            self.project = (os.environ.get("GEMINI_VERTEX_PROJECT")
                            or os.environ.get("GOOGLE_CLOUD_PROJECT")
                            or gcloud_project())
            if not self.project:
                raise RuntimeError(
                    "falta el proyecto de GCP: exporta GEMINI_VERTEX_PROJECT o deja "
                    "hecho `gcloud config set project <id>`")
        else:
            clave = os.environ.get("GEMINI_API_KEY")
            if not clave:
                raise RuntimeError(
                    "falta GEMINI_API_KEY: ponla en el entorno o en el .env del repo")
            self.provider = "gemini"
            self._clave = clave

    def _url_y_cabeceras(self) -> tuple[str, dict]:
        """Lo unico que cambia entre backends. El cuerpo es identico en los dos: si
        difiriera, las dos corridas dejarian de ser comparables."""
        if self.backend != "vertex":
            return (f"{GEMINI_BASE}/models/{self.model}:generateContent",
                    {"content-type": "application/json",
                     "x-goog-api-key": self._clave})
        host = (VERTEX_HOST if self.location == "global"
                else f"{self.location}-{VERTEX_HOST}")
        url = (f"https://{host}/v1beta1/projects/{self.project}"
               f"/locations/{self.location}/publishers/google/models/"
               f"{self.model}:generateContent")
        # `x-goog-user-project`: con credenciales de usuario, Vertex responde 403
        # "requires a quota project" sin ella, y el mensaje se lee como falta de plan.
        return url, {"content-type": "application/json",
                     "Authorization": f"Bearer {self._token_vigente()}",
                     "x-goog-user-project": self.project}

    def _token_vigente(self) -> str:
        ahora = time.monotonic()
        if not self._token or ahora - self._token_pedido >= VERTEX_TOKEN_TTL:
            self._token = gcloud_access_token()
            self._token_pedido = ahora
        return self._token

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
                if error.code == 401 and self.backend == "vertex" and not ultimo:
                    # `gcloud auth print-access-token` devuelve un token cacheado, que
                    # puede venir ya a mitad de su hora de vida: contar el TTL desde
                    # que se pide no basta. Aqui si se arregla reintentando, porque lo
                    # primero que se hace es tirar el token y pedir otro. En AI Studio
                    # un 401 es una clave mala y no se reintenta.
                    print("  [401] token caducado, pidiendo otro a gcloud", flush=True)
                    self._token = ""
                    continue
                if error.code not in GEMINI_RETRY_STATUS or ultimo:
                    detalle = error.read().decode(errors="replace")[:400]
                    raise RuntimeError(
                        f"HTTP {error.code} de Gemini: {detalle}") from error
                print(f"  [reintento {intento + 1}/{RETRY_ATTEMPTS - 1}] "
                      f"HTTP {error.code}, esperando {espera:.0f}s", flush=True)
            except (urllib.error.URLError, TimeoutError) as error:
                # `TimeoutError` no es `URLError`: un timeout de lectura del socket se
                # escapaba del manejo y mataba el proceso a mitad de rejilla. Es la
                # misma clase de fallo transitorio que un URLError y se trata igual.
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
        url, cabeceras = self._url_y_cabeceras()
        datos = post_json(url, cabeceras, payload)
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


def build_client(model: str, provider: str = "auto", max_tokens: int = 2048,
                 thinking_budget: int | None = None):
    """Un solo punto donde se decide el cliente, para que los corredores no tengan
    que saber de proveedores. El nombre del modelo basta: `gemini-*` va a Gemini y
    todo lo demas a Anthropic, salvo que se fuerce `--provider`."""
    if provider == "vertex":
        return GeminiClient(model=model, max_tokens=max_tokens,
                            thinking_budget=thinking_budget, backend="vertex")
    if provider == "gemini" or (provider == "auto" and model.startswith("gemini")):
        return GeminiClient(model=model, max_tokens=max_tokens,
                            thinking_budget=thinking_budget)
    return AnthropicClient(model=model, provider=provider, max_tokens=max_tokens)
