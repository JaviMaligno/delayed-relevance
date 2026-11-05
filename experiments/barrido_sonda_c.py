"""Barrido gratis (sin modelos) de `invalidation_k` y seeds para la sonda C con compactacion.

Busca configuraciones en que, con la trayectoria PERFECTA, el aviso de correccion cae
antes de una compactacion (15, 30, 45) y el paso decisivo -- el primer paso dependiente,
el unico que existe si el agente acierta -- cae despues. Con k=10 el aviso llega en el
paso 10 y el decisivo en el 11, antes de cualquier compactacion: la sonda no probaba la
compactacion (precheck del 5-nov-2026).

Para cada configuracion valida se cuentan ademas los pasos dependientes de la cascada
del agente sordo (los que existen si el agente no aplica la correccion) que caen tras
la compactacion: es la senal por repeticion si el brazo falla.

Uso: PYTHONPATH=src python experiments/barrido_sonda_c.py [--ks 1 40] [--seeds 0 19]
"""
from __future__ import annotations

import argparse

try:  # como script o importado desde los tests
    from precheck_compaction import COMPACTACIONES, Perfecto, Politica
    from run_compaction import construir_env, episodio
except ImportError:
    from experiments.precheck_compaction import COMPACTACIONES, Perfecto, Politica
    from experiments.run_compaction import construir_env, episodio


def evaluar(seed: int, k: int) -> dict | None:
    try:
        env = construir_env("C", seed, k)
    except ValueError:
        return None
    paso_store = env.invalidation_from - k
    perfecto = episodio(env, Perfecto(env), "C")
    aviso = perfecto["paso_aviso"]
    deps = perfecto["pasos_dependientes"]
    if not deps:
        return {"seed": seed, "k": k, "store": paso_store, "aviso": aviso, "decisivo": None,
                "valida": False}
    decisivo = deps[0]
    compactacion = next((c for c in COMPACTACIONES if aviso < c <= decisivo), None)
    env = construir_env("C", seed, k)
    sordo = episodio(env, Politica(olvida=False, oye_avisos=False), "C")
    cascada = sordo["pasos_dependientes"]
    tras = [d for d in cascada if compactacion is not None and d >= compactacion]
    return {"seed": seed, "k": k, "store": paso_store, "aviso": aviso, "decisivo": decisivo,
            "compactacion": compactacion, "valida": compactacion is not None,
            "cascada": len(cascada), "cascada_tras": len(tras),
            "suelo_sordo": sordo["score"]}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ks", nargs=2, type=int, default=[1, 40])
    p.add_argument("--seeds", nargs=2, type=int, default=[0, 19])
    args = p.parse_args()
    validas = []
    for seed in range(args.seeds[0], args.seeds[1] + 1):
        for k in range(args.ks[0], args.ks[1] + 1):
            r = evaluar(seed, k)
            if r and r["valida"]:
                validas.append(r)
    print(f"{len(validas)} configuraciones validas (aviso < compactacion <= paso decisivo)\n")
    print("seed  k  store aviso compact. decisivo  cascada  cascada_tras  suelo_sordo")
    for r in sorted(validas, key=lambda r: (-r["cascada_tras"], r["k"])):
        print(f"{r['seed']:4} {r['k']:2} {r['store']:6} {r['aviso']:5} {r['compactacion']:8} "
              f"{r['decisivo']:8} {r['cascada']:8} {r['cascada_tras']:13} {r['suelo_sordo']:12.3f}")


if __name__ == "__main__":
    main()
