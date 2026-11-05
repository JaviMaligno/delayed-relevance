"""Agregado por brazo del experimento de compactacion, con IC95 de Wilson.

La unidad de la metrica es la de cada sonda: en C, el PASO DEPENDIENTE (como en
`report_probeC.py`); en A, el episodio cuyo paso puntuado depende de la cuarentena en
su trayectoria real (`materializa`). Se da tambien, para C, el PRIMER paso dependiente
por episodio, que es el que la correccion decide; los siguientes solo existen si el
agente ya fallo, asi que contarlos pesa la cascada.

La tasa de consulta va siempre al lado del acierto: si un brazo `*_lookup` casi no
consulta, su resultado mide la pereza del modelo, no el metodo.

Uso: python experiments/report_compaction.py results/compaction/partial_*.json
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

ORDEN = ["react", "skillstate", "summary", "fresh_lookup", "hybrid_lookup", "summary_lookup"]


def wilson(aciertos: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de Wilson: con n pequeno y tasas cerca de 0 o 1 (el caso de esta sonda)
    el de Wald da intervalos fuera de [0, 1] o de anchura cero."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = aciertos / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    medio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centro - medio), min(1.0, centro + medio))


def _pct(a: int, n: int) -> str:
    if n == 0:
        return "   -"
    lo, hi = wilson(a, n)
    return f"{a}/{n} {100 * a / n:5.1f}% [{100 * lo:4.1f}-{100 * hi:5.1f}]"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("ficheros", nargs="+")
    args = p.parse_args()

    for fichero in args.ficheros:
        datos = json.loads(Path(fichero).read_text(encoding="utf-8"))
        sonda = Path(fichero).name.split("_")[1]
        por_brazo: dict[str, list[dict]] = defaultdict(list)
        for clave, d in datos.items():
            por_brazo[clave.split(":")[0]].append(d)
        print(f"\n{Path(fichero).name}  (sonda {sonda})\n")
        print(f"{'brazo':15} {'eps':>3} {'metrica (IC95 Wilson)':>30} {'1er dep.':>22} "
              f"{'score':>6} {'consulta':>9} {'portantes':>10} {'sin acc.':>8} {'trunc.':>6} "
              f"{'entrada ef./ep':>14} {'cache_read/ep':>13} {'USD lista/ep':>12} "
              f"{'s/ep':>6} {'s/llamada':>9}")
        for brazo in sorted(por_brazo, key=lambda b: ORDEN.index(b) if b in ORDEN else 99):
            eps = por_brazo[brazo]
            n = len(eps)
            aciertos = sum(e["aciertos"] for e in eps)
            dependientes = sum(e["dependientes"] for e in eps)
            primeros = [e.get("primer_dependiente") for e in eps if e.get("primer_dependiente")]
            primer = (_pct(sum(1 for x in primeros if x == "correcta"), len(primeros))
                      if sonda == "C" else "-")
            pasos = sum(e["pasos"] for e in eps)
            consultas = sum(e["consultas"] for e in eps)
            llamadas = sum(e["llamadas"] for e in eps)
            print(f"{brazo:15} {n:3} {_pct(aciertos, dependientes):>30} {primer:>22} "
                  f"{sum(e['score'] for e in eps) / n:6.3f} "
                  f"{100 * sum(e['pasos_con_consulta'] for e in eps) / pasos:8.1f}% "
                  f"{sum(e['consultas_portantes'] for e in eps):4}/{consultas:<5} "
                  f"{sum(e['sin_accion'] for e in eps):8} {sum(e['truncadas'] for e in eps):6} "
                  f"{sum(e['entrada_efectiva'] for e in eps) / n:14.0f} "
                  f"{sum(e['cache_read'] for e in eps) / n:13.0f} "
                  f"{sum(e['coste_lista_usd'] for e in eps) / n:12.4f} "
                  f"{sum(e['segundos'] for e in eps) / n:6.0f} "
                  f"{sum(e['segundos_llamadas'] for e in eps) / llamadas if llamadas else 0:9.1f}")
        modelos = sorted({m for eps in por_brazo.values() for e in eps for m in e["modelos"]})
        print(f"\nmodelos que contestaron: {modelos}")
        print("consulta = pasos con al menos un Lookup; portantes = consultas cuya respuesta "
              "traia el aviso (notice_id).")


if __name__ == "__main__":
    main()
