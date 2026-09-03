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
from dr.runtimes.memory import MemoryRuntime
from dr.runtimes.react import ReActRuntime
from dr.runtimes.skillstate import SkillStateRuntime
from dr.runtimes.stateful import StatefulRuntime


CONDICIONES = {
    "plain":    dict(sin_sonda=True),             # Tabla 1: sin sonda de relevancia diferida
    "none":     dict(),                          # sin campo: el hecho no tiene donde vivir
    "oracle":   dict(oracle_schema=True),        # campo que nombra lo que hay que guardar
    "hatch":    dict(hatch_schema=True),         # campo libre `notes`, sin decir para que
    "reminder": dict(reminder=True),             # el hecho repetido en cada observacion
    "invalidation": dict(invalidation=True),     # sonda C: correccion retroactiva
}


RUNTIMES = {
    "skillstate": lambda c, e: SkillStateRuntime(c, e.spec(), e.schema_fields()),
    "react": lambda c, e: ReActRuntime(c, e.spec()),
    "memory": lambda c, e: MemoryRuntime(c, e.spec()),
    "stateful": lambda c, e: StatefulRuntime(c, e.spec(), e.schema_fields()),
}


def episodio(cliente, seed: int, k: int, condicion: str, runtime: str = "skillstate") -> dict:
    kwargs = dict(CONDICIONES[condicion])
    sin_sonda = kwargs.pop("sin_sonda", False)
    invalidacion = kwargs.pop("invalidation", False)
    if invalidacion:
        kwargs["invalidation_k"] = k
    # `plain` reproduce la celda de la Tabla 1: mismo entorno, sin regla latente. Sirve
    # para comprobar si los 1.00 de esa tabla, medidos con 3-5 tiradas sueltas,
    # aguantan al repetir.
    env = Warehouse(horizon=50, seed=seed,
                    latent_k=None if (sin_sonda or invalidacion) else k, **kwargs)
    rt = RUNTIMES[runtime](cliente, env)
    env.reset()
    acierto = None
    resultados = []
    while not env.done:
        esperada = env.expected_action()
        es_dependiente = (env.dependent_step is not None
                          and env.step_index == env.dependent_step)
        accion, completions = rt.act(env.observe())
        correcta = accion is not None and accion.render() == esperada.render()
        if es_dependiente:
            acierto = correcta
        from dr.types import StepResult
        resultados.append(StepResult(step=env.step_index, actionable=env.observe().actionable,
                                     correct=correcta, prompt_tokens=0, output_tokens=0))
        env.apply(accion if accion is not None else esperada)
    if invalidacion and env.invalidation_from is not None:
        # METRICA DE PROMEDIO, no de evento: score sobre el tramo POSTERIOR al aviso.
        # Todos los Store de ese tramo dependen de haber aplicado la correccion, asi
        # que promedia quince o veinte eventos en vez de mirar uno solo.
        posteriores = [r for r in resultados if r.step > env.invalidation_from]
        return {"acierto": bool(acierto), "score": score(resultados),
                "score_posterior": score(posteriores),
                "n_posteriores": sum(1 for r in posteriores if r.actionable)}
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
    parser.add_argument("--condicion", default="oracle", choices=list(CONDICIONES))
    parser.add_argument("--runtime", default="skillstate", choices=list(RUNTIMES))
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
            pref = "" if args.runtime == "skillstate" else f"{args.runtime}:"
            clave = f"{pref}{args.model}:{args.condicion}:s{seed}:r{rep}:k{args.k}"
            if clave in hechos:
                continue
            r = episodio(cliente, seed, args.k, args.condicion, args.runtime)
            hechos[clave] = r
            ruta.write_text(json.dumps(hechos, indent=2))
            print(f"seed={seed} rep={rep}: {'OK' if r['acierto'] else 'X'} score={r['score']:.3f}",
                  flush=True)

    print("\nRUIDO DENTRO DE CADA SEED (mismo escenario, distintas tiradas)")
    tasas = []
    for seed in args.seeds:
        pref = "" if args.runtime == "skillstate" else f"{args.runtime}:"
        v = [x for c, x in hechos.items()
             if c.startswith(pref if pref else args.model)
             and f":{args.condicion}:s{seed}:" in c and c.endswith(f"k{args.k}")]
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
