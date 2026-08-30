"""Carga de credenciales desde un fichero .env local.

Existe para que la clave de API no tenga que pasar por la linea de comandos ni por
el historial de ninguna sesion: vive en .env, que esta en .gitignore.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env(path: Path | None = None) -> dict[str, str]:
    """Lee KEY=VALUE de un .env y lo vuelca en os.environ sin pisar lo ya definido.

    Devuelve las claves que ha cargado. Si el fichero no existe, no hace nada:
    el entorno del sistema sigue siendo una via valida.
    """
    env_path = path if path is not None else REPO_ROOT / ".env"
    if not env_path.exists():
        return {}
    loaded: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded
