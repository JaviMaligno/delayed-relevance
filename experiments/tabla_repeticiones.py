"""Arma la tabla de una tanda de repeticiones a partir de las trazas por episodio.

Cada celda es una media sobre TIRADAS, no sobre medias por seed: repetir la misma
seed da entre 0,715 y 0,960 porque los fallos encadenan, y promediar por seed antes
de tiempo esconde justo esa cola (spec 1.3, enmienda).

Solo entran episodios COMPLETOS y, si la traza lleva cabecera de condiciones, solo
los que coinciden con las condiciones pedidas: mezclar dos topes de salida en una
misma columna ya costo una conclusion falsa una vez.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics as st
from pathlib import Path

ORDEN = ["react", "memory", "stateful", "skillstate"]


def leer(fichero: Path) -> tuple[dict | None, list[dict]]:
    filas = []
    cabecera = None
    for linea in fichero.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except json.JSONDecodeError:
            return cabecera, []          # traza cortada: no vale
        if fila.get("kind") == "run_header":
            cabecera = fila.get("condiciones", {})
        else:
            filas.append(fila)
    return cabecera, filas


def episodios(directorio: Path, modelo: str, horizonte: int, runtime: str,
              exigidas: dict) -> list[dict]:
    patron = f"adj_T{horizonte}_{modelo}_{runtime}_s*.jsonl"
    salida = []
    for f in sorted(directorio.glob(patron)):
        cabecera, filas = leer(f)
        if len(filas) != horizonte:
            continue
        if cabecera is not None and any(cabecera.get(k) != v for k, v in exigidas.items()):
            continue
        accionables = [x for x in filas if x.get("actionable")]
        if not accionables:
            continue
        salida.append({
            "fichero": f.name,
            "sin_cabecera": cabecera is None,
            "score": sum(1 for x in accionables if x.get("correct")) / len(accionables),
            "prompt": sum(x.get("prompt_tokens") or 0 for x in filas),
            "truncados": sum(1 for x in filas if x.get("truncated")),
            "seed": int(re.search(r"_s(\d+)", f.name).group(1)),
        })
    return salida


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="claude-haiku-4-5")
    p.add_argument("--horizontes", default="50,200")
    p.add_argument("--dir", default="results")
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--apendice-b", dest="apendice_b", action="store_true", default=None)
    p.add_argument("--sin-telemetria", dest="sin_telemetria", action="store_true",
                   default=None)
    p.add_argument("--ruido", type=int, default=None)
    args = p.parse_args()

    exigidas = {k: v for k, v in (("max_tokens", args.max_tokens),
                                  ("apendice_b", args.apendice_b),
                                  ("sin_telemetria", args.sin_telemetria),
                                  ("ruido", args.ruido)) if v is not None}
    directorio = Path(args.dir)
    horizontes = [int(h) for h in args.horizontes.split(",")]

    print(f"modelo: {args.model}  condiciones exigidas: {exigidas or 'ninguna'}")
    print()
    print("| T | " + " | ".join(ORDEN) + " |")
    print("|---|" + "---|" * len(ORDEN))
    detalle = []
    for horizonte in horizontes:
        celdas = []
        for runtime in ORDEN:
            eps = episodios(directorio, args.model, horizonte, runtime, exigidas)
            if not eps:
                celdas.append("—")
                continue
            scores = [e["score"] for e in eps]
            media = st.mean(scores)
            sd = st.stdev(scores) if len(scores) > 1 else 0.0
            celdas.append(f"{media:.3f} ± {sd:.3f} (n={len(scores)})")
            detalle.append((horizonte, runtime, eps, media, sd))
        print(f"| {horizonte} | " + " | ".join(celdas) + " |")

    print()
    print("| T | runtime | n | seeds | prompt medio/episodio | truncados | sin cabecera |")
    print("|---|---|---|---|---|---|---|")
    for horizonte, runtime, eps, _, _ in detalle:
        seeds = sorted({e["seed"] for e in eps})
        prompt = st.mean(e["prompt"] for e in eps)
        print(f"| {horizonte} | {runtime} | {len(eps)} | {seeds} | {prompt:,.0f} | "
              f"{sum(e['truncados'] for e in eps)} | "
              f"{sum(1 for e in eps if e['sin_cabecera'])} |")


if __name__ == "__main__":
    main()
