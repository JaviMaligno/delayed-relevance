"""La interaccion runtime x modelo: las cuatro celdas de cada eje.

Todo el bloque 1 comparaba runtimes con un solo modelo. Al repetir los dos ejes donde
el estado explicito ganaba (sonda C y el entorno Repo) con el otro modelo, uno de los
dos se invierte. Este script reconstruye las tablas desde los ficheros de episodios,
para que ningun numero del documento de resultados tenga que copiarse a mano.

Metrica por eje:
  - repo         : score del episodio completo;
  - invalidation : score del tramo POSTERIOR al aviso (la sonda propiamente dicha).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean, stdev

MODELOS = {"Haiku 4.5": "claude-haiku-4-5", "Sonnet 5": "claude-sonnet-5"}
RUNTIMES = ["skillstate", "react"]


def episodios(datos: dict, entorno: str, condicion: str, runtime: str) -> list[float]:
    campo = "score_posterior" if condicion == "invalidation" else "score"
    prefijo = "repo:" if entorno == "repo" else ""
    prefijo += "" if runtime == "skillstate" else f"{runtime}:"
    valores = []
    for clave, fila in sorted(datos.items()):
        if not clave.startswith(prefijo) or f":{condicion}:" not in clave:
            continue
        # `react:` como prefijo tambien casa con claves de warehouse cuando se busca
        # repo, y al reves; el numero de segmentos antes del modelo lo desambigua.
        resto = clave[len(prefijo):]
        if not resto.startswith("claude-"):
            continue
        valores.append(fila[campo])
    return valores


def resumen(valores: list[float]) -> tuple[float, float, float, int]:
    n = len(valores)
    if n == 0:
        return 0.0, 0.0, 0.0, 0
    m = mean(valores)
    sd = stdev(valores) if n > 1 else 0.0
    return m, sd, 1.96 * sd / math.sqrt(n) if n > 1 else 0.0, n


def tabla(eje: str, entorno: str, condicion: str) -> dict[str, float]:
    print(f"\n{eje}")
    print(f"{'modelo':12} {'SKILL.state':>22} {'ReAct':>22} {'separacion':>12}")
    separaciones = {}
    for nombre, modelo in MODELOS.items():
        ruta = Path("results") / f"sampling_noise_{modelo}.json"
        if not ruta.exists():
            continue
        datos = json.loads(ruta.read_text())
        celdas = {rt: resumen(episodios(datos, entorno, condicion, rt)) for rt in RUNTIMES}
        if not all(c[3] for c in celdas.values()):
            print(f"{nombre:12} incompleto")
            continue
        a, b = celdas["skillstate"], celdas["react"]
        solapan = not (b[0] + b[2] < a[0] - a[2] or a[0] + a[2] < b[0] - b[2])
        separaciones[nombre] = a[0] - b[0]
        print(f"{nombre:12} "
              f"{a[0]:.3f}+-{a[1]:.3f} (n={a[3]:2}) "
              f"{b[0]:.3f}+-{b[1]:.3f} (n={b[3]:2}) "
              f"{a[0]-b[0]:+.3f} {'solapan' if solapan else 'DISJUNTOS'}")
    return separaciones


def main() -> None:
    ejes = [
        ("Sonda C: invalidacion retroactiva", "warehouse", "invalidation"),
        ("Entorno Repo: dependencias densas", "repo", "plain"),
    ]
    for eje, entorno, condicion in ejes:
        seps = tabla(eje, entorno, condicion)
        if len(seps) == 2:
            (n1, s1), (n2, s2) = seps.items()
            print(f"{'':12} interaccion ({n1} - {n2}): {s1 - s2:+.3f}"
                  + ("   INVIERTE EL SIGNO" if s1 * s2 < 0 else "   mismo signo"))
    print("\nUn eje replica entre modelos y el otro invierte. El runtime no es una")
    print("propiedad del problema: es una propiedad del par (problema, modelo).")


if __name__ == "__main__":
    main()
