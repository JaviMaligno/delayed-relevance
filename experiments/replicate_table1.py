"""Replica la Tabla 1 de SKILL.state sobre Warehouse. Corridas en serie, a proposito."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import anthropic

from dr.config import load_env
from dr.envs.warehouse import Warehouse
from dr.keepawake import keep_system_awake, release
from dr.llm import build_client, es_desbordamiento_de_contexto
from dr.metrics import aggregate, coste_efectivo, score
from dr.runner import run_episode
from dr.runtimes.memory import MemoryRuntime
from dr.runtimes.react import ReActRuntime
from dr.runtimes.skillstate import SkillStateRuntime
from dr.runtimes.stateful import StatefulRuntime


def finite(value: float) -> float | None:
    """La sd de una sola seed es NaN; json.dumps lo escribiria como NaN, que no es JSON."""
    return value if math.isfinite(value) else None


def build_runtimes(deep_merge: bool, declare_merge: bool = True) -> dict:
    """Los dos brazos con estado comparten profundidad de merge: si uno conserva las
    sub-claves hermanas y el otro no, la comparacion queda sesgada."""
    return {
        "react": lambda client, env: ReActRuntime(client, env.spec()),
        "memory": lambda client, env: MemoryRuntime(client, env.spec()),
        "stateful": lambda client, env: StatefulRuntime(
            client, env.spec(), env.schema_fields(), deep_merge=deep_merge),
        "skillstate": lambda client, env: SkillStateRuntime(
            client, env.spec(), env.schema_fields(), deep_merge=deep_merge,
            declare_merge=declare_merge),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, required=True)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=1,
                        help="Repeticiones por seed. Una seed es una tirada, no una "
                             "replica: con el prompt fijo, la unica fuente de "
                             "variacion entre episodios de la misma seed es el "
                             "muestreo del modelo, y es de decenas de puntos. El "
                             "acierto se agrega sobre repeticiones y la dispersion "
                             "entre seeds se reporta aparte. En greedy (Gemini a "
                             "temperature 0) basta 1.")
    parser.add_argument("--model", default="claude-haiku-4-5")
    parser.add_argument("--provider", default="auto",
                        choices=["auto", "api", "foundry", "gemini", "vertex"])
    parser.add_argument("--max-tokens", type=int, default=600,
                        help="Tope de salida por llamada. Sus totales de la Tabla 1 "
                             "implican respuestas cortas; 2048 disparaba el coste "
                             "y, en los brazos con historia, la densidad.")
    parser.add_argument("--merge", default="deep", choices=["deep", "shallow"],
                        help="Profundidad del merge de estado. shallow reproduce el "
                             "borrado prematuro sin que el modelo se equivoque.")
    parser.add_argument("--no-declare-merge", action="store_true",
                        help="No decir al modelo como funciona el merge. Es la "
                             "condicion que produjo 0.62 en la corrida de humo.")
    parser.add_argument("--only", nargs="*", default=None,
                        help="Correr solo estos runtimes.")
    parser.add_argument("--long-spec", action="store_true",
                        help="Procedimiento largo (~4.900 tokens), por encima del "
                             "prefijo minimo cacheable de 4.096. Sin esto la tabla de "
                             "coste solo mide el caso en que el bloque de sistema no "
                             "cachea en ningun brazo.")
    parser.add_argument("--thinking-budget", type=int, default=None,
                        help="Solo Gemini. Tokens de razonamiento interno; 0 lo apaga. Cuenta contra el tope de salida, asi que sin acotarlo el truncamiento se lee como fallo del metodo.")
    parser.add_argument("--apendice-b", action="store_true",
                        help="Cierra los dos huecos de I4: eventos de mantenimiento que "
                             "obligan a Move, y rechazo de acciones invalidas con error "
                             "local. La diferencia contra la variante sin bandera es la "
                             "medida de cuanto pesaba el hueco.")
    parser.add_argument("--sin-telemetria", action="store_true",
                        help="Generador de su Algoritmo 2: todos los pasos accionables. "
                             "Nuestra telemetria como paso propio es el hueco 3 de I4.")
    parser.add_argument("--ruido", type=int, default=0,
                        help="Distractores del Apendice C anexados a cada observacion, "
                             "bajo su cabecera. Su Experimento 2 usa 0, 5, 20 y 50.")
    parser.add_argument("--out", default="results")
    args = parser.parse_args()

    load_env()
    awake = keep_system_awake()
    print(f"suspension del sistema inhibida: {awake}", flush=True)

    client = build_client(args.model, args.provider, args.max_tokens,
                          thinking_budget=args.thinking_budget)
    print(f"proveedor: {client.provider}  modelo: {args.model}", flush=True)
    Path(args.out).mkdir(exist_ok=True)
    table: dict[str, dict[str, object]] = {}

    # Checkpoint por episodio: una corrida larga que se cae por un fallo de red no
    # puede perder todo lo ya pagado. Al relanzar, los episodios ya hechos se saltan.
    stem = f"T{args.horizon}_{args.model}_{client.provider}" + ("_longspec" if args.long_spec else "")
    if args.merge != "deep":
        stem += f"_{args.merge}"
    if args.no_declare_merge:
        stem += "_undeclared"
    if args.sin_telemetria:
        stem += "_alg2"
    if args.ruido:
        stem += f"_ruido{args.ruido}"
    if args.apendice_b:
        # Otro entorno, otro fichero: mezclarlos seria comparar dos tareas
        # distintas dentro de la misma celda.
        stem += "_apb"
    # El tope de salida y el presupuesto de pensamiento cambian lo que se mide, asi
    # que no pueden compartir fichero de checkpoint: si lo comparten, la calibracion
    # lee como "ya hecho" lo medido con el otro ajuste. Solo se anaden cuando se
    # apartan del valor por defecto, para no invalidar lo ya guardado.
    if args.max_tokens != 600:
        stem += f"_mt{args.max_tokens}"
    if args.thinking_budget is not None:
        stem += f"_tb{args.thinking_budget}"
    partial_path = Path(args.out) / f"partial_{stem}.json"
    done: dict[str, dict] = {}
    if partial_path.exists():
        done = json.loads(partial_path.read_text())
        print(f"reanudando: {len(done)} episodios ya completados", flush=True)

    runtimes = build_runtimes(args.merge == "deep", not args.no_declare_merge)
    if args.only:
        runtimes = {k: v for k, v in runtimes.items() if k in args.only}
    for name, build in runtimes.items():
        scores, prompts, totals = [], [], []
        brutos, efectivos = [], []
        overflowed: list[int] = []
        por_seed: dict[int, list[float]] = {}
        for seed in range(args.seeds):
            for rep in range(args.repeats):
                key = f"{name}:{seed}:{rep}"
                # Las corridas anteriores a las repeticiones guardaron "name:seed".
                # Se aceptan como la repeticion 0 para no re-pagar lo ya medido.
                if rep == 0 and key not in done and f"{name}:{seed}" in done:
                    key = f"{name}:{seed}"
                if key in done:
                    cached = done[key]
                    if "entrada_bruta" in cached:
                        brutos.append(cached["entrada_bruta"])
                        efectivos.append(cached["entrada_efectiva"])
                    if cached.get("overflowed"):
                        overflowed.append(seed)
                    else:
                        scores.append(cached["score"])
                        por_seed.setdefault(seed, []).append(cached["score"])
                        prompts.append(cached["avg_prompt"])
                        totals.append(cached["total"])
                    print(f"{name} seed={seed} rep={rep} (cacheado)", flush=True)
                    continue
                env = Warehouse(horizon=args.horizon, seed=seed, long_spec=args.long_spec,
                                apendice_b=args.apendice_b,
                                sin_telemetria=args.sin_telemetria,
                                ruido=args.ruido)
                try:
                    traza = Path(args.out) / f"traza_{stem}_{name}_s{seed}r{rep}.jsonl"
                    traza.unlink(missing_ok=True)
                    results = run_episode(env, build(client, env), traza=traza,
                                          condiciones={
                                              "model": args.model, "provider": client.provider,
                                              "max_tokens": args.max_tokens,
                                              "thinking_budget": args.thinking_budget,
                                              "horizon": args.horizon, "seed": seed,
                                              "runtime": name, "merge": args.merge,
                                              "apendice_b": args.apendice_b,
                                              "sin_telemetria": args.sin_telemetria,
                                              "ruido": args.ruido, "long_spec": args.long_spec,
                                          })
                except anthropic.BadRequestError as error:
                    if "prompt is too long" not in str(error).lower():
                        raise
                    print(f"{name} seed={seed} rep={rep} DESBORDA la ventana de contexto", flush=True)
                    overflowed.append(seed)
                    done[key] = {"overflowed": True}
                    partial_path.write_text(json.dumps(done, indent=2))
                    continue
                truncs = sum(r.truncated for r in results)
                if truncs:
                    print(f"  AVISO {name} seed={seed}: {truncs} respuestas truncadas "
                          f"por el tope de salida", flush=True)
                scores.append(score(results))
                prompts.append(sum(r.prompt_tokens for r in results) / len(results))
                totals.append(sum(r.prompt_tokens + r.output_tokens for r in results))
                cst = coste_efectivo(results)
                brutos.append(cst['tokens_brutos'])
                efectivos.append(cst['entrada_efectiva'])
                done[key] = {
                    "truncadas": truncs,
                    "pasos": len(results),
                    "thinking": sum(r.thinking_tokens for r in results),
                    "entrada_bruta": brutos[-1],
                    "entrada_efectiva": efectivos[-1],
                    "score": scores[-1],
                    "avg_prompt": prompts[-1],
                    "total": totals[-1],
                    "overflowed": False,
                }
                partial_path.write_text(json.dumps(done, indent=2))
                print(f"{name} seed={seed} rep={rep} score={scores[-1]:.2f} tokens={totals[-1]}", flush=True)
        if scores:
            table[name] = {
                "score_mean": finite(aggregate(scores).mean),
                "score_sd": finite(aggregate(scores).sd),
                "avg_prompt_tokens": finite(aggregate(prompts).mean),
                "total_tokens": finite(aggregate(totals).mean),
                "overflowed_seeds": overflowed,
                "score_por_seed": {str(s): aggregate(v).mean for s, v in por_seed.items()},
                "sd_entre_seeds": finite(aggregate(
                    [aggregate(v).mean for v in por_seed.values()]).sd),
                "episodios": len(scores),
                "entrada_bruta": finite(aggregate(brutos).mean) if brutos else None,
                "entrada_efectiva": finite(aggregate(efectivos).mean) if efectivos else None,
            }
        else:
            table[name] = {
                "score_mean": None,
                "score_sd": None,
                "avg_prompt_tokens": None,
                "total_tokens": None,
                "overflowed_seeds": overflowed,
            }

    table["_meta"] = {"provider": client.provider, "model": args.model,
                      "horizon": args.horizon, "seeds": args.seeds,
                      "repeats": args.repeats,
                      "thinking_budget": args.thinking_budget,
                      "max_tokens": args.max_tokens,
                      "merge": args.merge,
                      "declare_merge": not args.no_declare_merge}
    path = Path(args.out) / f"table1_{stem}.json"
    path.write_text(json.dumps(table, indent=2))
    print(f"escrito {path}", flush=True)
    release()


if __name__ == "__main__":
    main()
