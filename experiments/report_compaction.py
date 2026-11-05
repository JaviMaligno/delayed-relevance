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
import re
from collections import Counter, defaultdict
from pathlib import Path

from dr.runtimes.compaction import palabras_de

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
              f"{'USD lista/ep':>12} {'entr. ESTIM./ep':>15} {'cache_read/ep':>13} "
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
                  f"{sum(e['coste_lista_usd'] for e in eps) / n:12.4f} "
                  f"{_estimada(eps) / n:15.0f} "
                  f"{sum(e['cache_read'] for e in eps) / n:13.0f} "
                  f"{sum(e['segundos'] for e in eps) / n:6.0f} "
                  f"{sum(e['segundos_llamadas'] for e in eps) / llamadas if llamadas else 0:9.1f}")
        print("\nconsultas que solo traian el id del aviso (en una linea del agente) y "
              "resumenes truncados:")
        for brazo, eps in por_brazo.items():
            print(f"  {brazo:15} con_id={sum(e.get('consultas_con_id_del_aviso', 0) for e in eps)} "
                  f"resumenes_truncados={sum(e.get('resumenes_truncados', 0) for e in eps)}")
        print("\nforma de las consultas (palabras por consulta; con identificador = numero "
              "de estanteria, SKU o notice_id):")
        for brazo, eps in por_brazo.items():
            textos = [t for e in eps for t in e.get("textos_consulta", [])]
            if not textos:
                continue
            dist = Counter(len(palabras_de(t)) for t in textos)
            con_id = sum(1 for t in textos if IDENTIFICADOR.search(t))
            print(f"  {brazo:15} n={len(textos)} palabras={dict(sorted(dist.items()))} "
                  f"con identificador={con_id}/{len(textos)} ({100 * con_id / len(textos):.0f}%)")
        modelos = sorted({m for eps in por_brazo.values() for e in eps for m in e["modelos"]})
        print(f"\nmodelos que contestaron: {modelos}")
        print("consulta = pasos con al menos un Lookup; portantes = consultas cuya respuesta "
              "traia la observacion del aviso.")
        print("USD lista = coste a precio de lista MEDIDO por el CLI (sin cachear la historia: "
              "claude -p manda un solo bloque).")
        print("entr. ESTIM. = ESTIMACION de tokens de entrada equivalentes con cache de prefijo "
              "ideal (comun con la llamada anterior a 0,1x, resto a 1,25x); no es una medida.")


IDENTIFICADOR = re.compile(r"SKU-[A-Za-z]|\b(?:COR|FAC)-\d+|\d")
"""Un numero suelto cuenta como estanteria: es lo unico numerico que el agente busca."""


def _estimada(eps: list[dict]) -> float:
    """Episodios anteriores al campo (piloto v1/v2) no lo tienen: se recurre a la cuenta
    con los multiplicadores sobre lo que el CLI declaro, y se avisa."""
    total = 0.0
    for e in eps:
        if "entrada_efectiva_estimada" in e:
            total += e["entrada_efectiva_estimada"]
        else:
            print(f"  (aviso: episodio sin entrada_efectiva_estimada; se usa la del CLI)")
            total += e["entrada_efectiva"]
    return total


if __name__ == "__main__":
    main()
