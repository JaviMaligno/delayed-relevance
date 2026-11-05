"""Compactar o consultar: corredor de las sondas A y C (`docs/diseno-compactacion-vs-transcript.md`).

Un episodio por (brazo, seed, repeticion), con checkpoint en
`results/compaction/partial_*.json`: relanzar reanuda sin repetir lo hecho.

Metrica por sonda, con la misma logica que los corredores del bloque 1:
- **A** (`probe_a.py`, escenarios estrictos): acierto en el paso dependiente, y si en
  la trayectoria REAL ese paso depende de la cuarentena (`materializa`).
- **C** (`diagnose_probeC.py` v2): pasos dependientes posteriores al aviso, con la
  correccion aplicada (`correcta`) o no (`sorda`, `otra`, `sin_accion`).

Ademas, por episodio: consultas, pasos con consulta y **consultas cuya respuesta traia
la linea portante** (el aviso, identificado por su `notice_id`). Es lo que distingue
"no consulto" de "consulto, vio la correccion y eligio el valor viejo".

Uso (lanzar con `exec`, ver README):
    cd <repo> && PYTHONPATH=src exec python experiments/run_compaction.py \
        --probe C --arms fresh_lookup --seeds 4 --reps 1 --client claude-cli
"""
from __future__ import annotations

import argparse
import copy
import json
import time
from pathlib import Path

from dr.envs.warehouse import Warehouse, event_field
from dr.keepawake import keep_system_awake, release
from dr.llm import CODEX_MODELO, build_client
from dr.metrics import score
from dr.runner import NO_OP
from dr.runtimes.compaction import BRAZOS
from dr.runtimes.react import ReActRuntime
from dr.runtimes.skillstate import SkillStateRuntime
from dr.types import StepResult

try:  # como script (experiments/ en sys.path) o importado desde los tests
    from diagnose_probeC import accion_sorda, actualiza
except ImportError:
    from experiments.diagnose_probeC import accion_sorda, actualiza

VERSION = 1
HORIZONTE = 50
K_POR_SONDA = {"A": 40, "C": 10}
SEEDS_POR_SONDA = {"A": [0, 3, 6], "C": [4, 10, 6]}
MODELO_POR_CLIENTE = {"claude-cli": "claude-haiku-5-5", "codex-cli": CODEX_MODELO}

FABRICAS = {
    **{nombre: (lambda clase: lambda c, e: clase(c, e.spec()))(clase)
       for nombre, clase in BRAZOS.items()},
    "react": lambda c, e: ReActRuntime(c, e.spec()),
    "skillstate": lambda c, e: SkillStateRuntime(c, e.spec(), e.schema_fields()),
}


def construir_env(sonda: str, seed: int, k: int) -> Warehouse:
    if sonda == "C":
        return Warehouse(horizon=HORIZONTE, seed=seed, invalidation_k=k)
    # Estricto, como la sonda L1 v3: el hecho importa por primera vez en t+k.
    return Warehouse(horizon=HORIZONTE, seed=seed, latent_k=k, latent_estricto=True)


def aviso(env: Warehouse, sonda: str) -> tuple[int, str]:
    """Paso del aviso portante y su `notice_id`, que identifica la linea en el
    transcript sin depender de como la formatee el runtime."""
    if sonda == "C":
        texto = env.script[env.invalidation_from].text
        return env.invalidation_from, event_field(texto, "notice_id") or ""
    return env.quarantine_from, event_field(env.quarantine_notice_text, "notice_id") or ""


def episodio(env: Warehouse, rt, sonda: str, traza: Path | None = None,
             condiciones: dict | None = None) -> dict:
    """Cruza el entorno con el runtime y mide la sonda. `rt` puede ser cualquier objeto
    con `act`: el precheck lo usa con politicas deterministas, sin modelo."""
    env.reset()
    paso_aviso, notice_id = aviso(env, sonda)
    # Sonda C: la creencia del agente sordo se congela ANTES de que el aviso vacie la
    # estanteria y solo la mueven las acciones del propio agente (diagnose_probeC v2).
    creencia = dict(env.shelves)
    cajas = {"correcta": 0, "sorda": 0, "otra": 0, "sin_accion": 0}
    primer_dependiente = None
    dependientes = 0
    pasos_dependientes: list[int] = []
    # Sonda A.
    acierto_a = materializa = None
    resultados: list[StepResult] = []
    tot = {"truncadas": 0, "sin_accion": 0, "llamadas": 0, "prompt": 0, "cache_read": 0,
           "cache_write": 0, "salida": 0, "thinking": 0, "coste_lista_usd": 0.0,
           "segundos_llamadas": 0.0, "consultas": 0, "pasos_con_consulta": 0,
           "consultas_portantes": 0, "consultas_tras_aviso": 0}
    modelos: set[str] = set()
    inicio = time.monotonic()
    if traza is not None:
        traza.parent.mkdir(parents=True, exist_ok=True)
        with open(traza, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": "run_header", "condiciones": condiciones or {}},
                                ensure_ascii=False) + "\n")
    while not env.done:
        obs = env.observe()
        esperada = env.expected_action()
        sorda = accion_sorda(obs, creencia) if sonda == "C" else None
        es_el_paso = sonda == "A" and env.step_index == env.dependent_step
        if es_el_paso:
            sin = copy.deepcopy(env)
            sin.quarantined_shelf = None
            materializa = esperada.render() != sin.expected_action().render()
        n_consultas = len(getattr(rt, "consultas", []))
        n_compact = len(getattr(rt, "compactaciones", []))
        accion, completions = rt.act(obs)
        consultas = getattr(rt, "consultas", [])[n_consultas:]
        compactado = len(getattr(rt, "compactaciones", [])) > n_compact
        rend = accion.render() if accion is not None else None
        correcta = rend == esperada.render()
        caja = None
        dependiente = False
        if sonda == "C":
            posterior = env.invalidation_from is not None and env.step_index > env.invalidation_from
            dependiente = posterior and obs.actionable and esperada.render() != sorda.render()
            if dependiente:
                dependientes += 1
                pasos_dependientes.append(obs.step)
                caja = ("sin_accion" if accion is None else "correcta" if correcta
                        else "sorda" if rend == sorda.render() else "otra")
                cajas[caja] += 1
                primer_dependiente = primer_dependiente or caja
        elif es_el_paso:
            acierto_a = correcta
            dependiente = True
        portantes = [bool(notice_id) and any(notice_id in l for l in c.lineas) for c in consultas]
        tot["truncadas"] += sum(1 for c in completions if c.truncated)
        tot["sin_accion"] += accion is None
        tot["llamadas"] += len(completions)
        tot["prompt"] += sum(c.prompt_tokens for c in completions)
        tot["cache_read"] += sum(c.cache_read for c in completions)
        tot["cache_write"] += sum(c.cache_write for c in completions)
        tot["salida"] += sum(c.output_tokens for c in completions)
        tot["thinking"] += sum(getattr(c, "thinking_tokens", 0) for c in completions)
        tot["coste_lista_usd"] += sum(getattr(c, "cost_usd", 0.0) for c in completions)
        tot["segundos_llamadas"] += sum(getattr(c, "segundos", 0.0) for c in completions)
        tot["consultas"] += len(consultas)
        tot["pasos_con_consulta"] += bool(consultas)
        tot["consultas_portantes"] += sum(portantes)
        tot["consultas_tras_aviso"] += len(consultas) if obs.step > paso_aviso else 0
        modelos.update(c.model_version for c in completions if getattr(c, "model_version", ""))
        resultados.append(StepResult(step=obs.step, actionable=obs.actionable, correct=correcta,
                                     prompt_tokens=0, output_tokens=0))
        if traza is not None:
            with open(traza, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "http": 200, "step": obs.step, "actionable": obs.actionable,
                    "compactado": compactado, "dependiente": dependiente, "caja": caja,
                    "esperado": esperada.render(),
                    "sordo": sorda.render() if sorda is not None else None,
                    "ejecutado": rend, "correct": correcta,
                    "consultas": [{"consulta": c.consulta, "coincidencias": c.coincidencias,
                                   "portante": p, "lineas": c.lineas}
                                  for c, p in zip(consultas, portantes)],
                    "raw": {"respuestas": [c.text for c in completions]},
                    "observation": obs.text,
                    "prompt_tokens": sum(c.prompt_tokens for c in completions),
                    "output_tokens": sum(c.output_tokens for c in completions),
                    "cache_read": sum(c.cache_read for c in completions),
                    "cache_write": sum(c.cache_write for c in completions),
                    "thinking_tokens": sum(getattr(c, "thinking_tokens", 0) for c in completions),
                    "truncated": sum(1 for c in completions if c.truncated),
                    "segundos": [round(getattr(c, "segundos", 0.0), 2) for c in completions],
                    "model_version": next((c.model_version for c in completions
                                           if getattr(c, "model_version", "")), ""),
                }, ensure_ascii=False) + "\n")
        if sonda == "C" and accion is not None:
            actualiza(creencia, accion)
        # Un paso sin accion es NoOp, como en el runner principal: nunca la correcta.
        env.apply(accion if accion is not None else NO_OP)

    if sonda == "C":
        metrica = {"aciertos": cajas["correcta"], "dependientes": dependientes,
                   "metrica": cajas["correcta"] / dependientes if dependientes else None,
                   "primer_dependiente": primer_dependiente, **cajas}
    else:
        metrica = {"aciertos": int(bool(acierto_a and materializa)),
                   "dependientes": int(bool(materializa)),
                   "metrica": (1.0 if acierto_a else 0.0) if materializa else None,
                   "acierto_dependiente": bool(acierto_a), "materializa": materializa}
    efectiva = tot["prompt"] + tot["cache_read"] * 0.10 + tot["cache_write"] * 1.25
    return {**metrica, "score": score(resultados), **tot, "entrada_efectiva": efectiva,
            "paso_aviso": paso_aviso, "pasos_dependientes": pasos_dependientes,
            "compactaciones": list(getattr(rt, "compactaciones", [])),
            "sin_accion_tras_consultas": getattr(rt, "sin_accion_tras_consultas", 0),
            "parches_invalidos": getattr(rt, "invalid_patches", 0),
            "modelos": sorted(modelos), "segundos": time.monotonic() - inicio,
            "pasos": len(resultados)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--probe", choices=["A", "C"], required=True)
    p.add_argument("--arms", nargs="*", default=list(FABRICAS), choices=list(FABRICAS))
    p.add_argument("--seeds", nargs="*", type=int, default=None)
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--client", choices=["claude-cli", "codex-cli"], default="claude-cli")
    p.add_argument("--model", default=None)
    p.add_argument("--k", type=int, default=None,
                   help="latent_k (A, por defecto 40) o invalidation_k (C, por defecto 10)")
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--out", default="results/compaction")
    args = p.parse_args()

    # Sin load_env a proposito: los CLIs usan la suscripcion y el .env solo trae claves
    # de API, que aqui no deben llegar a ningun sitio.
    modelo = args.model or MODELO_POR_CLIENTE[args.client]
    k = args.k if args.k is not None else K_POR_SONDA[args.probe]
    seeds = args.seeds if args.seeds is not None else SEEDS_POR_SONDA[args.probe]
    cliente = build_client(modelo, args.client, args.max_tokens)
    print(f"suspension del sistema inhibida: {keep_system_awake()}", flush=True)
    print(f"cliente: {cliente.provider}  modelo: {modelo}  sonda {args.probe} k={k}", flush=True)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # El tope de salida y k cambian lo medido: van en el nombre del checkpoint para que
    # una corrida con otro ajuste no lea como hecho lo medido con este.
    nombre = f"{args.probe}_k{k}_{args.client}_{modelo}_mt{args.max_tokens}_v{VERSION}"
    ruta = out / f"partial_{nombre}.json"
    hechos: dict = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    if hechos:
        print(f"reanudando: {len(hechos)} episodios ya completados", flush=True)
    try:
        for brazo in args.arms:
            for seed in seeds:
                for rep in range(args.reps):
                    clave = f"{brazo}:s{seed}:r{rep}"
                    if clave in hechos:
                        print(f"{clave} (hecho)", flush=True)
                        continue
                    env = construir_env(args.probe, seed, k)
                    traza = out / "trazas" / f"{nombre}_{brazo}_s{seed}_r{rep}.jsonl"
                    d = episodio(env, FABRICAS[brazo](cliente, env), args.probe, traza, {
                        "experimento": "compaction", "version": VERSION, "sonda": args.probe,
                        "k": k, "brazo": brazo, "seed": seed, "rep": rep,
                        "cliente": args.client, "modelo": modelo,
                        "max_tokens": args.max_tokens, "horizonte": HORIZONTE})
                    hechos[clave] = d
                    ruta.write_text(json.dumps(hechos, indent=2), encoding="utf-8")
                    print(f"{clave} metrica={d['aciertos']}/{d['dependientes']} "
                          f"score={d['score']:.2f} consultas={d['consultas']} "
                          f"portantes={d['consultas_portantes']} sin_accion={d['sin_accion']} "
                          f"truncadas={d['truncadas']} llamadas={d['llamadas']} "
                          f"{d['segundos']:.0f}s modelos={d['modelos']}", flush=True)
    finally:
        release()


if __name__ == "__main__":
    main()
