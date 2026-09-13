"""Sonda A: relevancia diferida.

En el paso t el entorno anuncia una cuarentena; en t+k esa estanteria es la libre mas
baja y la accion correcta es saltarsela. `k` es la variable barrida. El paso
dependiente y la estanteria son los mismos para todos los valores de k, asi que lo
unico que cambia es la distancia entre la informacion y su uso.

Ademas del score se reporta la METRICA QUE IMPORTA: si el agente acerto en el paso
dependiente concreto. El score global lo diluye entre 170 eventos; el acierto en ese
paso es la medicion directa.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import anthropic

from dr.config import load_env
from dr.envs.warehouse import Warehouse
from dr.keepawake import keep_system_awake, release
from dr.llm import build_client, es_desbordamiento_de_contexto
from dr.metrics import aggregate, coste_efectivo, score
from dr.runtimes.memory import MemoryRuntime
from dr.runtimes.react import ReActRuntime
from dr.runtimes.skillstate import SkillStateRuntime
from dr.runtimes.stateful import StatefulRuntime
from dr.types import StepResult


def build_runtimes() -> dict:
    return {
        "react": lambda c, e: ReActRuntime(c, e.spec()),
        "memory": lambda c, e: MemoryRuntime(c, e.spec()),
        "stateful": lambda c, e: StatefulRuntime(c, e.spec(), e.schema_fields()),
        "skillstate": lambda c, e: SkillStateRuntime(c, e.spec(), e.schema_fields()),
    }


def run_episode_probe(env, runtime) -> tuple[list[StepResult], bool | None]:
    """Como run_episode, pero registra aparte el acierto en el paso dependiente."""
    env.reset()
    resultados: list[StepResult] = []
    acierto_dependiente: bool | None = None
    while not env.done:
        obs = env.observe()
        esperada = env.expected_action()
        es_el_paso = env.step_index == env.dependent_step
        accion, completions = runtime.act(obs)
        correcta = accion is not None and accion.render() == esperada.render()
        if es_el_paso:
            acierto_dependiente = correcta
        resultados.append(
            StepResult(
                step=obs.step,
                actionable=obs.actionable,
                correct=correcta,
                prompt_tokens=sum(c.prompt_tokens for c in completions),
                output_tokens=sum(c.output_tokens for c in completions),
                state_size=runtime.state_size(),
                truncated=sum(1 for c in completions if c.truncated),
            )
        )
        env.apply(accion if accion is not None else esperada)
    return resultados, acierto_dependiente


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=50)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=1,
                        help="Repeticiones por seed; ver replicate_table1.py. Con una "
                             "tirada por seed esta sonda dio un 60% que al repetirlo "
                             "resulto ser 21%.")
    parser.add_argument("--ks", nargs="*", type=int, default=[1, 5, 10, 20, 40])
    parser.add_argument("--control", action="store_true",
                        help="Cuarentena sobre una estanteria que nunca es portante.")
    parser.add_argument("--model", default="claude-haiku-4-5")
    parser.add_argument("--provider", default="auto",
                        choices=["auto", "api", "foundry", "gemini"])
    parser.add_argument("--max-tokens", type=int, default=600)
    parser.add_argument("--oracle-schema", action="store_true",
                        help="Dar al esquema un campo para la cuarentena (cota superior).")
    parser.add_argument("--hatch-schema", action="store_true",
                        help="Campo `notes` de texto libre: sitio sin decir para que.")
    parser.add_argument("--reminder", action="store_true",
                        help="Repetir el aviso en cada observacion posterior.")
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--out", default="results")
    args = parser.parse_args()

    load_env()
    print(f"suspension del sistema inhibida: {keep_system_awake()}", flush=True)
    client = build_client(args.model, args.provider, args.max_tokens)
    sufijo = ("_control" if args.control else "") + ("_oracle" if args.oracle_schema else "") + ("_hatch" if args.hatch_schema else "") + ("_reminder" if args.reminder else "")
    print(f"proveedor: {client.provider}  modelo: {args.model}{sufijo}", flush=True)

    Path(args.out).mkdir(exist_ok=True)
    runtimes = build_runtimes()
    if args.only:
        runtimes = {k: v for k, v in runtimes.items() if k in args.only}

    partial_path = Path(args.out) / f"partial_probeA_T{args.horizon}_{args.model}{sufijo}.json"
    done: dict[str, dict] = {}
    if partial_path.exists():
        done = json.loads(partial_path.read_text())
        print(f"reanudando: {len(done)} episodios ya completados", flush=True)

    # Se parte de lo ya escrito: correr con --only no debe borrar las celdas de los
    # otros runtimes. Reconstruir la tabla desde cero destruyo la sonda de skillstate.
    path = Path(args.out) / f"probeA_T{args.horizon}_{args.model}{sufijo}.json"
    tabla: dict[str, dict] = json.loads(path.read_text()) if path.exists() else {}
    for name, build in runtimes.items():
        for k in args.ks:
            scores, aciertos = [], []
            for seed, rep in [(s, r) for s in range(args.seeds)
                              for r in range(args.repeats)]:
                clave = f"{name}:k{k}:{seed}:{rep}"
                # Compatibilidad con lo medido antes de las repeticiones.
                if rep == 0 and clave not in done and f"{name}:k{k}:{seed}" in done:
                    clave = f"{name}:k{k}:{seed}"
                if clave in done:
                    scores.append(done[clave]["score"])
                    aciertos.append(done[clave]["dependiente"])
                    print(f"{clave} (cacheado)", flush=True)
                    continue
                env = Warehouse(horizon=args.horizon, seed=seed, latent_k=k,
                                latent_control=args.control,
                                oracle_schema=args.oracle_schema,
                                hatch_schema=args.hatch_schema,
                                reminder=args.reminder)
                try:
                    resultados, acierto = run_episode_probe(env, build(client, env))
                except (anthropic.BadRequestError, RuntimeError) as error:
                    if not es_desbordamiento_de_contexto(error):
                        raise
                    print(f"{clave} DESBORDA la ventana", flush=True)
                    continue
                s = score(resultados)
                truncs = sum(r.truncated for r in resultados)
                if truncs:
                    print(f"  AVISO {clave}: {truncs} respuestas truncadas", flush=True)
                scores.append(s)
                aciertos.append(bool(acierto))
                tam = [r.state_size for r in resultados]
                coste = coste_efectivo(resultados)
                done[clave] = {"score": s, "dependiente": bool(acierto),
                               "entrada_bruta": coste["tokens_brutos"],
                               "entrada_efectiva": coste["entrada_efectiva"],
                               "salida": sum(r.output_tokens for r in resultados),
                               "sigma_inicial": tam[0] if tam else 0,
                               "sigma_final": tam[-1] if tam else 0,
                               "sigma_max": max(tam) if tam else 0}
                partial_path.write_text(json.dumps(done, indent=2))
                print(f"{clave} score={s:.2f} paso_dependiente={'OK' if acierto else 'FALLO'}",
                      flush=True)
            if scores:
                tabla[f"{name}:k{k}"] = {
                    "score_mean": aggregate(scores).mean,
                    "score_sd": aggregate(scores).sd if len(scores) > 1 else 0.0,
                    "acierto_dependiente": sum(aciertos) / len(aciertos),
                    "n": len(scores),
                }

    tabla["_meta"] = {"provider": client.provider, "model": args.model,
                      "horizon": args.horizon, "seeds": args.seeds, "ks": args.ks,
                      "control": args.control, "oracle_schema": args.oracle_schema, "hatch_schema": args.hatch_schema,
                      "max_tokens": args.max_tokens}
    path.write_text(json.dumps(tabla, indent=2))
    print(f"escrito {path}", flush=True)
    release()


if __name__ == "__main__":
    main()
