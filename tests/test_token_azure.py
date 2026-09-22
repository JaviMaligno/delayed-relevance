"""Que ocho episodios en paralelo no se queden sin token de Foundry.

Con `DefaultAzureCredential` cada proceso recorria toda la cadena de credenciales
--incluida una sonda de red a IMDS-- y volvia a invocar el CLI. Con ocho procesos a la
vez, `az` empezo a no responder a tiempo: `AzureCliCredential: Failed to invoke the
Azure CLI`, y ocho episodios de R2 murieron con la sesion perfectamente viva.

El remedio es el mismo que ya tiene Vertex: pedir el token una vez, guardarlo mientras
dure, reintentar los fallos transitorios del CLI y esperar --no morir-- si lo que ha
caducado es la sesion, que se arregla con `az login` en otra terminal.
"""
import json
import time

import httpx2 as httpx
import pytest

import dr.llm as llm


def _respuesta_az(token="token-azure", vida=3600):
    return json.dumps({"accessToken": token, "expires_on": int(time.time()) + vida})


@pytest.fixture(autouse=True)
def _sin_cache():
    llm.olvidar_token_azure()
    yield
    llm.olvidar_token_azure()


def test_el_token_se_pide_una_vez_y_se_reutiliza(monkeypatch):
    llamadas = {"n": 0}

    def _az_falso(*args):
        llamadas["n"] += 1
        return _respuesta_az()

    monkeypatch.setattr(llm, "_az", _az_falso)
    assert llm.azure_access_token() == "token-azure"
    assert llm.azure_access_token() == "token-azure"
    assert llamadas["n"] == 1, "el segundo episodio no puede volver a invocar el CLI"


def test_un_fallo_transitorio_del_cli_se_reintenta(monkeypatch):
    intentos = {"n": 0}
    esperas = []

    def _az_falso(*args):
        intentos["n"] += 1
        if intentos["n"] < 3:
            raise RuntimeError("az account get-access-token fallo: Failed to invoke")
        return _respuesta_az()

    monkeypatch.setattr(llm, "_az", _az_falso)
    monkeypatch.setattr(llm.time, "sleep", lambda s: esperas.append(s))
    assert llm.azure_access_token() == "token-azure"
    assert intentos["n"] == 3
    assert esperas, "tiene que haber esperado entre intentos"


def test_una_sesion_caducada_espera_en_vez_de_morir(monkeypatch):
    intentos = {"n": 0}
    esperas = []

    def _az_falso(*args):
        intentos["n"] += 1
        if intentos["n"] < 3:
            raise RuntimeError("az fallo: Please run 'az login' to setup account")
        return _respuesta_az()

    monkeypatch.setattr(llm, "_az", _az_falso)
    monkeypatch.setattr(llm.time, "sleep", lambda s: esperas.append(s))
    assert llm.azure_access_token() == "token-azure"
    assert sum(esperas) >= llm.ESPERA_ENTRE_AVISOS, "una caducidad se espera, no se reintenta a ciegas"


def test_un_fallo_persistente_acaba_muriendo(monkeypatch):
    def _az_falso(*args):
        raise RuntimeError("az account get-access-token fallo: Failed to invoke")

    monkeypatch.setattr(llm, "_az", _az_falso)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        llm.azure_access_token()


def test_se_respeta_la_caducidad_real_del_token(monkeypatch):
    # `az` entrega el token que ya tiene en cache, con la vida que le quede. Guardarlo
    # 45 minutos contados desde que se pide dejo morir ocho episodios con un 401.
    llamadas = {"n": 0}

    def _az_falso(*args):
        llamadas["n"] += 1
        return _respuesta_az(vida=120)          # le quedan dos minutos

    monkeypatch.setattr(llm, "_az", _az_falso)
    llm.azure_access_token()
    llm.azure_access_token()
    assert llamadas["n"] == 2, "un token a punto de caducar no se puede reutilizar"


class _Mensajes:
    def __init__(self, fallos):
        self.fallos = fallos
        self.intentos = 0

    def create(self, **kwargs):
        self.intentos += 1
        if self.intentos <= self.fallos:
            respuesta = httpx.Response(401, request=httpx.Request("POST", "https://x"))
            raise llm.anthropic.AuthenticationError("401 caducado", response=respuesta,
                                                    body=None)

        class _Uso:
            input_tokens = 3
            output_tokens = 1
            cache_read_input_tokens = 0
            cache_creation_input_tokens = 0

        class _Bloque:
            type = "text"
            text = "ok"

        class _Respuesta:
            content = [_Bloque()]
            usage = _Uso()
            stop_reason = "end_turn"
            model = "claude-haiku-4-5"

        return _Respuesta()


def _cliente_foundry(monkeypatch, fallos, con_clave=False):
    for nombre in llm.FOUNDRY_ENV_VARS:
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "un-recurso")
    if con_clave:
        monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "ficticia")
    mensajes = _Mensajes(fallos)

    class _Stub:
        def __init__(self, **kwargs):
            self.messages = mensajes

    monkeypatch.setattr(llm.anthropic, "AnthropicFoundry", _Stub)
    return llm.AnthropicClient(model="claude-haiku-4-5"), mensajes


def test_un_401_con_entra_id_tira_el_token_y_reintenta(monkeypatch):
    olvidos = []
    monkeypatch.setattr(llm, "olvidar_token_azure", lambda: olvidos.append(1))
    cliente, mensajes = _cliente_foundry(monkeypatch, fallos=1)
    assert cliente.complete(system="s", user="u").text == "ok"
    assert mensajes.intentos == 2
    assert olvidos, "hay que tirar el token caducado antes de reintentar"


def test_un_401_que_persiste_acaba_fallando(monkeypatch):
    monkeypatch.setattr(llm, "olvidar_token_azure", lambda: None)
    cliente, _ = _cliente_foundry(monkeypatch, fallos=10)
    with pytest.raises(llm.anthropic.AuthenticationError):
        cliente.complete(system="s", user="u")


def test_con_clave_de_api_un_401_no_se_reintenta(monkeypatch):
    # Ahi el 401 es una clave mala, y eso no se arregla pidiendo otro token.
    cliente, mensajes = _cliente_foundry(monkeypatch, fallos=1, con_clave=True)
    with pytest.raises(llm.anthropic.AuthenticationError):
        cliente.complete(system="s", user="u")
    assert mensajes.intentos == 1
