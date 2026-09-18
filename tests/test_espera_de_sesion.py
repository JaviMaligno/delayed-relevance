"""Que una tanda larga sobreviva a que caduque la sesion de gcloud.

La credencial SSO dura unas horas y una rejilla dura mas. Hoy han muerto cuatro
tandas por eso, una de 50 episodios: el cliente pedia token, `gcloud` contestaba
`Reauthentication failed. cannot prompt during non-interactive execution`, y el
proceso se caia con todo lo pendiente.

Workload Identity Federation lo arreglaria de raiz, pero el alta esta bloqueada por
permisos de IAM. Mientras tanto, la diferencia entre perder una tanda y no perderla es
esta: ante una caducidad, **esperar** a que alguien renueve la sesion en vez de morir.
No es lo mismo que reintentar a ciegas -- un error de gcloud que NO sea caducidad
sigue matando el proceso al instante, porque esperar no lo arregla.
"""
import pytest

import dr.llm as llm

REAUTH = ("gcloud auth print-access-token fallo: ERROR: "
          "(gcloud.auth.print-access-token) There was a problem refreshing your "
          "current auth tokens: Reauthentication failed. cannot prompt during "
          "non-interactive execution.")


def test_una_caducidad_espera_y_sigue_cuando_vuelve_la_sesion(monkeypatch):
    intentos = {"n": 0}
    esperas = []

    def _gcloud_falso(*args):
        intentos["n"] += 1
        if intentos["n"] < 3:
            raise RuntimeError(REAUTH)
        return "token-bueno"

    monkeypatch.setattr(llm, "_gcloud", _gcloud_falso)
    monkeypatch.setattr(llm.time, "sleep", lambda s: esperas.append(s))
    assert llm.gcloud_access_token() == "token-bueno"
    assert intentos["n"] == 3
    assert esperas, "tiene que haber esperado entre intentos"


def test_un_error_de_gcloud_que_no_es_caducidad_no_espera(monkeypatch):
    # Un proyecto mal configurado o un gcloud roto no se arreglan esperando: tienen
    # que reventar en el segundo cero, no dentro de tres horas.
    esperas = []

    def _gcloud_falso(*args):
        raise RuntimeError("gcloud auth print-access-token fallo: command not found")

    monkeypatch.setattr(llm, "_gcloud", _gcloud_falso)
    monkeypatch.setattr(llm.time, "sleep", lambda s: esperas.append(s))
    with pytest.raises(RuntimeError, match="command not found"):
        llm.gcloud_access_token()
    assert esperas == []


def test_si_la_sesion_no_vuelve_nunca_acaba_fallando(monkeypatch):
    # Esperar indefinidamente es peor que fallar: la tanda parece viva y no lo esta.
    esperas = []

    def _gcloud_falso(*args):
        raise RuntimeError(REAUTH)

    monkeypatch.setattr(llm, "_gcloud", _gcloud_falso)
    monkeypatch.setattr(llm.time, "sleep", lambda s: esperas.append(s))
    with pytest.raises(RuntimeError, match="Reauthentication"):
        llm.gcloud_access_token()
    assert sum(esperas) <= llm.ESPERA_MAXIMA_SESION + 1
