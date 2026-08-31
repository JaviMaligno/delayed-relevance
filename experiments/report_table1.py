"""Compara nuestra replica contra la Tabla 1 del paper y saca la tabla del articulo.

Reporta las tres cosas juntas a proposito: score, densidad de contexto y numero de
truncamientos. Un score sin su densidad no dice nada, porque medio experimento
consiste en estar en el mismo regimen que ellos; y un score sin sus truncamientos
puede ser un artefacto del tope de salida en vez de un resultado.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Tabla 1 del paper (Warehouse, Gemini-3-Flash): score, prompt medio, tokens totales.
PAPER = {
    "react": {10: (0.90, 3249, 9438), 25: (0.92, 6052, 42689), 50: (0.88, 11931, 171658)},
    "memory": {10: (1.00, 3300, 9972), 25: (0.99, 6357, 43067), 50: (0.93, 7582, 131455)},
    "stateful": {10: (1.00, 3430, 10337), 25: (1.00, 5858, 41238), 50: (0.94, 11594, 170992)},
    "skillstate": {10: (1.00, 1775, 5870), 25: (1.00, 1736, 14714), 50: (0.96, 1773, 30151)},
}
ORDER = ["react", "memory", "stateful", "skillstate"]
ETIQUETA = {
    "react": "ReAct (historia completa)",
    "memory": "Memory (resumen)",
    "stateful": "Stateful (estado + historia)",
    "skillstate": "SKILL.state (solo estado)",
}


def truncations(log_path: Path | None) -> dict[str, int]:
    if log_path is None or not log_path.exists():
        return {}
    found: dict[str, int] = {}
    for line in log_path.read_text(errors="ignore").splitlines():
        m = re.search(r"AVISO (\w+) seed=(\d+): (\d+) respuestas truncadas", line)
        if m:
            found[f"{m.group(1)}:{m.group(2)}"] = int(m.group(3))
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results")
    parser.add_argument("--model", default="claude-haiku-4-5")
    parser.add_argument("--provider", default="foundry")
    parser.add_argument("--horizons", nargs="*", type=int, default=[10, 25, 50])
    parser.add_argument("--log", default=None, help="Log de la corrida, para contar truncamientos.")
    args = parser.parse_args()

    tablas = {}
    for h in args.horizons:
        path = Path(args.results) / f"table1_T{h}_{args.model}_{args.provider}.json"
        if path.exists():
            tablas[h] = json.loads(path.read_text())
    if not tablas:
        print("no hay resultados todavia")
        return

    trunc = truncations(Path(args.log) if args.log else None)
    horizontes = sorted(tablas)

    print(f"Replica de la Tabla 1 — {args.model} via {args.provider}")
    print(f"Horizontes: {horizontes}. Formato: nuestro (ellos).\n")

    print("SCORE")
    print(f"{'runtime':30} " + " ".join(f"{'T=' + str(h):>18}" for h in horizontes))
    for name in ORDER:
        celdas = []
        for h in horizontes:
            v = tablas[h].get(name, {})
            mean, sd = v.get("score_mean"), v.get("score_sd")
            suyo = PAPER[name][h][0]
            celdas.append(
                "n/a".rjust(18) if mean is None
                else f"{mean:.2f}±{sd or 0:.2f} ({suyo:.2f})".rjust(18)
            )
        print(f"{ETIQUETA[name]:30} " + " ".join(celdas))

    print("\nDENSIDAD DE CONTEXTO (prompt medio, y ratio contra ellos)")
    print(f"{'runtime':30} " + " ".join(f"{'T=' + str(h):>18}" for h in horizontes))
    for name in ORDER:
        celdas = []
        for h in horizontes:
            v = tablas[h].get(name, {})
            nuestro = v.get("avg_prompt_tokens")
            suyo = PAPER[name][h][1]
            celdas.append(
                "n/a".rjust(18) if nuestro is None
                else f"{nuestro:.0f} ({nuestro / suyo:.2f}x)".rjust(18)
            )
        print(f"{ETIQUETA[name]:30} " + " ".join(celdas))

    if trunc:
        print("\nTRUNCAMIENTOS POR TOPE DE SALIDA (episodios afectados)")
        por_runtime: dict[str, list[int]] = {}
        for clave, cuenta in trunc.items():
            por_runtime.setdefault(clave.split(":")[0], []).append(cuenta)
        for name in ORDER:
            cuentas = por_runtime.get(name, [])
            estado = "ninguno" if not cuentas else f"{len(cuentas)} episodios, {sum(cuentas)} respuestas"
            print(f"{ETIQUETA[name]:30} {estado}")
        print("\nUn score de un brazo con truncamientos hay que contrastarlo contra sus")
        print("episodios limpios antes de leerlo como resultado.")

    print("\nSALVEDADES QUE VAN EN EL ARTICULO")
    print("- SkillExecBench no tiene codigo publico: el entorno es una reimplementacion")
    print("  desde la descripcion de su §4.1. Se iguala la densidad de contexto, no el")
    print("  contenido literal de sus eventos.")
    print("- Seguimos por encima de su densidad. El ratio va en la tabla, no en una nota.")
    print("- Su columna de tokens totales es inconsistente con su propia columna de prompt")
    print("  medio (horizonte x prompt medio excede su total por ~3.5x en todos los")
    print("  horizontes), asi que solo el prompt medio es comparable directamente.")


if __name__ == "__main__":
    main()
