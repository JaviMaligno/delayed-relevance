"""Evita que el sistema se suspenda mientras corre una rejilla larga.

Una corrida de horas contra una API es tiempo de espera, no de CPU, asi que Windows
la considera inactividad y entra en bajo consumo. En modern standby (S0) eso no deja
ni rastro en el registro de eventos, asi que se manifiesta como una corrida
inexplicablemente lenta.

Solo pide "no suspender el sistema": la pantalla puede apagarse con normalidad. La
peticion es por proceso y se libera al terminar; no cambia la configuracion de
energia del equipo.
"""
from __future__ import annotations

import ctypes
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


def keep_system_awake() -> bool:
    """Devuelve True si la peticion se acepto. En otros sistemas no hace nada."""
    if not sys.platform.startswith("win"):
        return False
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
    result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
    if result == 0:
        # Away mode no esta disponible en todas las maquinas; sin el sigue valiendo.
        result = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        )
    return result != 0


def release() -> None:
    """Devuelve el control al sistema."""
    if sys.platform.startswith("win"):
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
