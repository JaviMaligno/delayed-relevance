"""Comprueba que cada traza corresponde a un episodio COMPLETO antes de agregar nada.

Existe por un fallo real: al agregar la tabla se contaban ficheros como episodios, y
uno de `memory` en T=200 tenia 163 pasos de 200 -- habia muerto a mitad durante una
caducidad de sesion. Entro en la media como si estuviera entero. El sesgo fue de dos
milesimas, pero podria no haberlo sido, y nada lo habria dicho.

Uso:  verificar_trazas.py [--dir results] [--arreglar]
Sin `--arreglar` solo informa; con la bandera, borra las trazas incompletas para que
la reanudacion las vuelva a medir.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re


def revisar(directorio: str) -> list[tuple[str, str]]:
    problemas = []
    for f in sorted(glob.glob(os.path.join(directorio, "adj_T*.jsonl"))):
        m = re.search(r"adj_T(\d+)_", os.path.basename(f))
        if not m:
            continue
        esperadas = int(m.group(1))
        try:
            with open(f, encoding="utf-8") as fh:
                # La cabecera de condiciones no es un paso: si se contara, toda traza
                # nueva pareceria tener uno de mas y el verificador daria falsos
                # positivos justo sobre las trazas mejor instrumentadas.
                filas = 0
                for linea in fh:
                    if not linea.strip():
                        continue
                    try:
                        if json.loads(linea).get("kind") == "run_header":
                            continue
                    except json.JSONDecodeError:
                        problemas.append((f, "linea JSON corrupta"))
                        break
                    filas += 1
                else:
                    if filas != esperadas:
                        problemas.append((f, f"{filas} pasos, esperados {esperadas}"))
                continue
        except OSError as error:
            problemas.append((f, f"ilegible: {error}"))
            continue
    return problemas


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default="results")
    p.add_argument("--arreglar", action="store_true",
                   help="Borra las trazas incompletas para que se vuelvan a medir.")
    args = p.parse_args()
    problemas = revisar(args.dir)
    total = len(glob.glob(os.path.join(args.dir, "adj_T*.jsonl")))
    if not problemas:
        print(f"{total} trazas, todas completas")
        return
    print(f"{total} trazas, {len(problemas)} INCOMPLETAS:")
    for f, motivo in problemas:
        print(f"  {os.path.basename(f)}: {motivo}")
        if args.arreglar:
            os.remove(f)
            marca = f + ".trazas-leidas"
            if os.path.exists(marca):
                os.remove(marca)
            print("    borrada; la reanudacion la volvera a medir")
    raise SystemExit(0 if args.arreglar else 1)


if __name__ == "__main__":
    main()
