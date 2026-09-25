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
from dr.runner import NO_OP
from dr.types import StepResult


def build_runtimes() -> dict:
    return {
        "react": lambda c, e: ReActRuntime(c, e.spec()),
        "memory": lambda c, e: MemoryRuntime(c, e.spec()),
        "stateful": lambda c, e: StatefulRuntime(c, e.spec(), e.schema_fields()),
        "skillstate": lambda c, e: SkillStateRuntime(c, e.spec(), e.schema_fields()),
    }


VERSION_SONDA = 3
"""1: un paso sin accion aplicaba la accion correcta. 2: aplica NoOp y deja traza.
3: escenarios estrictos (el hecho importa por primera vez en t+k) y, por episodio, si el
paso puntuado depende del hecho en la trayectoria REAL."""


def resumen_celda(episodios: list[dict]) -> dict:
    """Cuentas de una celda con la metrica que publica el paper.

    Un episodio cuyo paso puntuado no depende del hecho en su trayectoria real
    (`materializa` falso) no prueba nada: se cuenta aparte y su acierto no suma. Se
    dan la tasa condicionada (sobre los que materializan) y la conjunta (sobre todos),
    porque la exclusion depende de lo que hizo el propio runtime antes y cambia la
    poblacion comparada (revision adversarial 7)."""
    n = len(episodios)
    mat = [e for e in episodios if e.get("materializa")]
    aciertos = sum(1 for e in mat if e["dependiente"])
    excl = [e for e in episodios if not e.get("materializa")]
    return {"episodios": n, "materializados": len(mat), "aciertos": aciertos,
            "excluidos": len(excl), "aciertos_excluidos": sum(1 for e in excl if e["dependiente"]),
            "acierto_condicionado": aciertos / len(mat) if mat else None,
            "acierto_conjunto": aciertos / n if n else None}


def run_episode_probe(env, runtime, traza=None,
                      condiciones: dict | None = None):
    """Como run_episode, pero registra aparte el acierto en el paso dependiente.

    Devuelve tambien `info`: si en el paso puntuado la cuarentena cambia la accion
    correcta sobre el mundo REAL (`materializa`) -- si no, el paso no prueba nada y el
    acierto no cuenta -- y cuantas veces la cambio antes de ese paso."""
    import copy
    env.reset()
    if traza is not None and condiciones:
        with open(traza, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": "run_header", "condiciones": condiciones}) + "\n")
    resultados: list[StepResult] = []
    acierto_dependiente: bool | None = None
    materializa: bool | None = None
    dependencias_previas = 0
    while not env.done:
        obs = env.observe()
        esperada = env.expected_action()
        es_el_paso = env.step_index == env.dependent_step
        if env.quarantined_shelf is not None and env.quarantine_from is not None \
                and env.step_index > env.quarantine_from:
            sin = copy.deepcopy(env)
            sin.quarantined_shelf = None
            depende = esperada.render() != sin.expected_action().render()
            if es_el_paso:
                materializa = depende
            elif env.step_index < env.dependent_step and depende:
                dependencias_previas += 1
        accion, completions = runtime.act(obs)
        correcta = accion is not None and accion.render() == esperada.render()
        if es_el_paso:
            acierto_dependiente = correcta
        if traza is not None:
            with open(traza, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "http": 200, "step": obs.step, "actionable": obs.actionable,
                    "es_el_paso": es_el_paso,
                    "materializa": materializa if es_el_paso else None,
                    "esperado": esperada.render(),
                    "ejecutado": accion.render() if accion is not None else None,
                    "correct": correcta,
                    "raw": {"respuestas": [c.text for c in completions]},
                    "observation": obs.text,
                    "prompt_tokens": sum(c.prompt_tokens for c in completions),
                    "output_tokens": sum(c.output_tokens for c in completions),
                    "cache_read": sum(c.cache_read for c in completions),
                    "cache_write": sum(c.cache_write for c in completions),
                    "truncated": sum(1 for c in completions if c.truncated),
                    "model_version": next((c.model_version for c in completions
                                           if getattr(c, "model_version", "")), ""),
                }, ensure_ascii=False) + "\n")
        resultados.append(
            StepResult(
                step=obs.step,
                actionable=obs.actionable,
                correct=correcta,
                prompt_tokens=sum(c.prompt_tokens for c in completions),
                # Sin estos dos, el coste agregado de L1 ignoraba la cache (revision 6).
                cache_read=sum(c.cache_read for c in completions),
                cache_write=sum(c.cache_write for c in completions),
                output_tokens=sum(c.output_tokens for c in completions),
                state_size=runtime.state_size(),
                truncated=sum(1 for c in completions if c.truncated),
            )
        )
        # Un paso sin accion es NoOp, como en el runner principal. Antes aplicaba la
        # accion CORRECTA y reparaba gratis el mundo del brazo que fallaba (revision
        # adversarial 5); las medidas hechas antes de este cambio lo llevan dentro.
        env.apply(accion if accion is not None else NO_OP)
    return resultados, acierto_dependiente, {"materializa": materializa,
                                             "dependencias_previas": dependencias_previas}


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
                        choices=["auto", "api", "foundry", "gemini", "vertex"])
    parser.add_argument("--max-tokens", type=int, default=600)
    parser.add_argument("--oracle-schema", action="store_true",
                        help="Dar al esquema un campo para la cuarentena (cota superior).")
    parser.add_argument("--hatch-schema", action="store_true",
                        help="Campo `notes` de texto libre: sitio sin decir para que.")
    parser.add_argument("--reminder", action="store_true",
                        help="Repetir el aviso en cada observacion posterior.")
    parser.add_argument("--thinking-budget", type=int, default=None,
                        help="Solo Gemini. La Tabla 1 se midio con 0; correr la sonda "
                             "con el razonamiento por defecto la mide en otra "
                             "condicion que el resto del trabajo.")
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--seed-list", nargs="*", type=int, default=None,
                        help="Seeds concretas en vez de range(--seeds): con escenarios "
                             "estrictos no todas las seeds tienen uno.")
    parser.add_argument("--estricto", action="store_true",
                        help="Escenarios donde el hecho importa por primera vez en t+k.")
    parser.add_argument("--out", default="results")
    args = parser.parse_args()

    load_env()
    print(f"suspension del sistema inhibida: {keep_system_awake()}", flush=True)
    client = build_client(args.model, args.provider, args.max_tokens,
                          thinking_budget=args.thinking_budget)
    sufijo = ("_control" if args.control else "") + ("_oracle" if args.oracle_schema else "") + ("_hatch" if args.hatch_schema else "") + ("_reminder" if args.reminder else "")
    # El tope de salida y el presupuesto de razonamiento CAMBIAN lo que se mide, asi
    # que no pueden compartir fichero de checkpoint: si lo comparten, una corrida nueva
    # lee como "ya hecho" lo medido con el otro ajuste y la celda mezcla condiciones.
    # Paso de verdad: relanzar esta sonda con presupuesto 0 reanudo sobre 34 episodios
    # medidos con el razonamiento por defecto. Mismo fallo que ya tenia replicate_table1
    # y que aqui faltaba.
    if args.max_tokens != 600:
        sufijo += f"_mt{args.max_tokens}"
    if args.thinking_budget is not None:
        sufijo += f"_tb{args.thinking_budget}"
    # La version del runner va en el nombre: sin ella, una re-medida leeria como "ya
    # hecho" lo medido con el runner que reparaba el mundo.
    sufijo += ("_estricto" if args.estricto else "") + f"_v{VERSION_SONDA}"
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
            scores, aciertos, episodios_celda = [], [], []
            seeds = args.seed_list if args.seed_list is not None else range(args.seeds)
            for seed, rep in [(s, r) for s in seeds for r in range(args.repeats)]:
                clave = f"{name}:k{k}:{seed}:{rep}"
                # Compatibilidad con lo medido antes de las repeticiones.
                if rep == 0 and clave not in done and f"{name}:k{k}:{seed}" in done:
                    clave = f"{name}:k{k}:{seed}"
                if clave in done:
                    scores.append(done[clave]["score"])
                    aciertos.append(done[clave]["dependiente"])
                    episodios_celda.append(done[clave])
                    print(f"{clave} (cacheado)", flush=True)
                    continue
                env = Warehouse(horizon=args.horizon, seed=seed, latent_k=k,
                                latent_control=args.control,
                                oracle_schema=args.oracle_schema,
                                hatch_schema=args.hatch_schema,
                                reminder=args.reminder, latent_estricto=args.estricto)
                traza = Path(args.out) / (f"l1v{VERSION_SONDA}_T{args.horizon}_{args.model}"
                                          f"{sufijo}_{name}_k{k}_s{seed}_r{rep}.jsonl")
                try:
                    resultados, acierto, info = run_episode_probe(
                        env, build(client, env), traza=traza, condiciones={
                            "sonda": "L1", "version_sonda": VERSION_SONDA,
                            "model": args.model, "provider": client.provider,
                            "runtime": name, "seed": seed, "rep": rep, "latent_k": k,
                            "horizon": args.horizon, "max_tokens": args.max_tokens,
                            "thinking_budget": args.thinking_budget,
                            "oracle_schema": args.oracle_schema,
                            "hatch_schema": args.hatch_schema, "reminder": args.reminder,
                            "control": args.control, "estricto": args.estricto})
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
                episodios_celda.append({"dependiente": bool(acierto),
                                        "materializa": info["materializa"]})
                tam = [r.state_size for r in resultados]
                coste = coste_efectivo(resultados)
                done[clave] = {"score": s, "dependiente": bool(acierto),
                               "materializa": info["materializa"],
                               "dependencias_previas": info["dependencias_previas"],
                               "truncadas": truncs,
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
                    # Sin filtrar, incluidos episodios que no prueban nada: solo como
                    # referencia historica. La metrica publicada es `celda`.
                    "acierto_dependiente_sin_filtrar": sum(aciertos) / len(aciertos),
                    "celda": resumen_celda(episodios_celda),
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
