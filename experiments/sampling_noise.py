"""Cuanto ruido de muestreo hay: la MISMA seed repetida N veces.

Todo el proyecto ha tratado cada seed como una replica independiente. No lo es: con
el prompt fijo, la unica fuente de variacion es el muestreo del modelo, y dos
corridas de la misma celda dieron 70% y 95%. Sin este numero no se puede decir si
una diferencia entre condiciones es real.

Separa dos varianzas que hasta ahora iban mezcladas:
  - entre seeds  : episodios distintos, escenarios distintos;
  - dentro de una seed: el mismo escenario, tiradas distintas del modelo.

Si la de dentro es comparable a la de entre, comparar condiciones con seeds distintas
no distingue efecto de ruido, y hace falta repetir.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from dr.config import load_env
from dr.envs.warehouse import Warehouse
from dr.keepawake import keep_system_awake, release
from dr.llm import AnthropicClient
from dr.metrics import score
from dr.runtimes.skillstate import SkillStateRuntime


def episodio(cliente, seed: int, k: int, oracle: bool) -> dict:
    env = Warehouse(horizon=50, seed=seed, latent_k=k, oracle_schema=oracle)
    rt = SkillStateRuntime(cliente, env.spec(), env.schema_fields())
    env.reset()
    acierto = None
    resultados = []
    while not env.done:
        esperada = env.expected_action()
        es_dependiente = env.step_index == env.dependent_step
        accion, completions = rt.act(env.observe())
        correcta = accion is not None and accion.render() == esperada.render()
        if es_dependiente:
            acierto = correcta
        from dr.types import StepResult
        resultados.append(StepResult(step=env.step_index, actionable=env.observe().actionable,
                                     correct=correcta, prompt_tokens=0, output_tokens=0))
        env.apply(accion if accion is not None else esperada)
    return {"acierto": bool(acierto), "score": score(resultados)}


def intervalo(aciertos: int, n: int) -> tuple[float, float]:
    """Wilson, que no colapsa a cero cuando p vale 0 o 1."""
    if n == 0:
        return 0.0, 0.0
    z = 1.96
    p = aciertos / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    margen = z / (1 + z * z / n) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centro - margen) * 100, min(1.0, centro + margen) * 100


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2],
                        help="Seeds a repetir. Pocas y muchas repeticiones, no al reves.")
    parser.add_argument("--repeats", type=int, default=8)
    parser.add_argument("--k", type=int, default=40)
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--oracle-schema", action="store_true", default=True)
    parser.add_argument("--max-tokens", type=int, default=600)
    args = parser.parse_args()

    load_env()
    keep_system_awake()
    cliente = AnthropicClient(model=args.model, max_tokens=args.max_tokens)
    ruta = Path("results") / f"sampling_noise_{args.model}.json"
    ruta.parent.mkdir(exist_ok=True)
    hechos: dict = json.loads(ruta.read_text()) if ruta.exists() else {}

    for seed in args.seeds:
        for rep in range(args.repeats):
            clave = f"{args.model}:s{seed}:r{rep}:k{args.k}"
            if clave in hechos:
                continue
            r = episodio(cliente, seed, args.k, args.oracle_schema)
            hechos[clave] = r
            ruta.write_text(json.dumps(hechos, indent=2))
            print(f"seed={seed} rep={rep}: {'OK' if r['acierto'] else 'X'} score={r['score']:.3f}",
                  flush=True)

    print("\nRUIDO DENTRO DE CADA SEED (mismo escenario, distintas tiradas)")
    tasas = []
    for seed in args.seeds:
        v = [x for c, x in hechos.items() if f":s{seed}:" in c and c.endswith(f"k{args.k}")]
        if not v:
            continue
        a = sum(x["acierto"] for x in v)
        lo, hi = intervalo(a, len(v))
        tasas.append(a / len(v))
        print(f"  seed {seed}: {a}/{len(v)} = {a/len(v)*100:3.0f}%  IC95 {lo:.0f}-{hi:.0f}%  "
              f"{' '.join('OK' if x['acierto'] else 'X' for x in v)}")

    if len(tasas) > 1:
        media = sum(tasas) / len(tasas)
        disp = max(tasas) - min(tasas)
        print(f"\n  tasa media entre seeds: {media*100:.0f}%")
        print(f"  dispersion ENTRE seeds : {disp*100:.0f} puntos")
        print("\nSi la dispersion entre seeds es del orden del ancho de los IC de cada seed,")
        print("las seeds no aportan informacion propia: comparar condiciones con seeds")
        print("distintas mide ruido de muestreo, no efecto.")
    release()


if __name__ == "__main__":
    main()
