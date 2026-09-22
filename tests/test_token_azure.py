"""Que ocho episodios en paralelo no se queden sin token de Foundry.

Con `DefaultAzureCredential` cada proceso recorria toda la cadena de credenciales
--incluida una sonda de red a IMDS-- y volvia a invocar el CLI. Con ocho procesos a la
vez, `az` empezo a no responder a tiempo: `AzureCliCredential: Failed to invoke the
Azure CLI`, y ocho episodios de R2 murieron con la sesion perfectamente viva.

El remedio es el mismo que ya tiene Vertex: pedir el token una vez, guardarlo mientras
dure, reintentar los fallos transitorios del CLI y esperar --no morir-- si lo que ha
caducado es la sesion, que se arregla con `az login` en otra terminal.
"""
import pytest

import dr.llm as llm


@pytest.fixture(autouse=True)
def _sin_cache():
    llm.olvidar_token_azure()
    yield
    llm.olvidar_token_azure()


def test_el_token_se_pide_una_vez_y_se_reutiliza(monkeypatch):
    llamadas = {"n": 0}

    def _az_falso(*args):
        llamadas["n"] += 1
        return "token-azure"

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
        return "token-azure"

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
        return "token-azure"

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
