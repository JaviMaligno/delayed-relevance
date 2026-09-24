"""Descomponer el score de la sonda C: la correccion, o todo lo demas.

El score del tramo posterior mezcla dos cosas muy distintas: si el agente aplico el
aviso de correccion, y si acerto el resto de pasos. Con el suelo medido —un agente
perfecto que ignora el aviso saca 0.931 / 0.893 / 1.000 en las seeds 0, 1 y 2— un
brazo que puntua POR DEBAJO de ese suelo no esta fallando la correccion: esta fallando
otra cosa, y su separacion frente a otro brazo no dice nada sobre invalidacion
retroactiva.

Clasifica cada paso accionable posterior al aviso en tres cajas:
  correcta : coincide con la accion esperada segun el estado VERDADERO;
  sorda    : coincide con lo que haria un agente perfecto que nunca oyo el aviso
             (creencia actualizada con las acciones del propio agente);
  otra     : ni una cosa ni la otra.

Y cuenta aparte los dos artefactos que contaminarian la medida: respuestas cortadas
por el tope de salida y respuestas de las que no se pudo extraer accion.

Version 2 (revision adversarial 5, hallazgo 1). La medida anterior no media lo que
publicaba: los pasos dependientes salian de la trayectoria de un agente sordo simulado,
los aciertos se calculaban como `dependientes - sordas` sin descontar pasos sin accion
ni `otra`, y un paso sin accion aplicaba la accion CORRECTA, reparando gratis el mundo
del brazo que fallaba. Un runtime que nunca contesta sacaba el 100 %. Ahora:

- un paso es **dependiente** si, en la trayectoria REAL, la accion correcta y la del
  agente sordo difieren; solo ahi se mide si el agente aplico la correccion;
- la medida primaria es POR EPISODIO: la caja del PRIMER paso dependiente, que es el
  que la correccion decide. En una trayectoria correcta hay uno por episodio; los
  siguientes aparecen cuando el agente ya fallo y su mundo diverge, asi que contarlos
  premia o castiga la cascada, no la correccion. Un episodio sin paso decisivo se
  cuenta aparte, nunca como acierto;
- cada paso dependiente cae en correcta / sorda / otra / sin_accion;
- un paso sin accion aplica NO_OP, como en el runner principal;
- cada episodio deja su traza por paso con cabecera de condiciones.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dr.config import load_env
from dr.envs.warehouse import SHELF_COUNT, Warehouse, event_field
from dr.keepawake import keep_system_awake, release
from dr.llm import build_client
from dr.runtimes.react import ReActRuntime
from dr.runtimes.skillstate import SkillStateRuntime
from dr.runner import NO_OP
from dr.types import Action

VERSION_SONDA = 2

RUNTIMES = {
    "skillstate": lambda c, e: SkillStateRuntime(c, e.spec(), e.schema_fields()),
    "react": lambda c, e: ReActRuntime(c, e.spec()),
}


def accion_sorda(obs, creencia: dict) -> Action:
    """Lo que haria un agente perfecto que nunca aplico el aviso de correccion."""
    if not obs.actionable:
        return Action(name="Wait")
    sku = event_field(obs.text, "sku") or ""
    if "inbound_pallet" in obs.text:
        libre = next(i for i in range(SHELF_COUNT) if creencia[i] is None)
        return Action(name="Store", args={"shelf": libre, "sku": sku,
                                          "units": int(event_field(obs.text, "units") or 0),
                                          "lot": event_field(obs.text, "lot") or ""})
    for i in range(SHELF_COUNT):
        if creencia[i] is not None and creencia[i][0] == sku:
            return Action(name="Ship", args={"shelf": i, "sku": sku})
    return Action(name="Wait")


def actualiza(creencia: dict, accion: Action) -> None:
    if accion.name == "Store":
        s = accion.args.get("shelf")
        if isinstance(s, int) and 0 <= s < SHELF_COUNT:
            creencia[s] = (str(accion.args.get("sku")), 0, "")
    elif accion.name == "Ship":
        s = accion.args.get("shelf")
        if isinstance(s, int) and 0 <= s < SHELF_COUNT:
            creencia[s] = None


def episodio(cliente, seed: int, k: int, runtime: str, fabrica=None, traza=None,
             condiciones: dict | None = None) -> dict:
    env = Warehouse(horizon=50, seed=seed, invalidation_k=k)
    rt = fabrica(env) if fabrica is not None else RUNTIMES[runtime](cliente, env)
    env.reset()
    # Mundo de referencia: el mismo episodio ejecutando siempre la accion correcta. No
    # entra en la medida; sirve para comprobar que un paso fallido no repara el mundo.
    ref = Warehouse(horizon=50, seed=seed, invalidation_k=k)
    ref.reset()
    # La creencia se congela ANTES de que el aviso vacie la estanteria y a partir de
    # ahi solo la mueven las acciones del propio agente: es su mundo si no oyo nada.
    creencia = dict(env.shelves)
    cajas = {"correcta": 0, "sorda": 0, "otra": 0, "sin_accion": 0}
    primer_dependiente = None
    truncadas = sin_accion_total = pasos = dependientes = mundo_distinto = 0
    efectiva = salida = 0.0
    if traza is not None and condiciones:
        with open(traza, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": "run_header", "condiciones": condiciones}) + "\n")
    while not env.done:
        obs = env.observe()
        esperada = env.expected_action()
        sorda = accion_sorda(obs, creencia)
        ref.observe()
        mundo_distinto += env.shelves != ref.shelves
        accion, completions = rt.act(obs)
        pasos += 1
        truncadas += sum(1 for c in completions if c.truncated)
        efectiva += sum(c.prompt_tokens + c.cache_read * 0.10
                        + c.cache_write * 1.25 for c in completions)
        salida += sum(c.output_tokens for c in completions)
        sin_accion_total += accion is None
        posterior = (env.invalidation_from is not None
                     and env.step_index > env.invalidation_from)
        dependiente = posterior and obs.actionable and esperada.render() != sorda.render()
        rend = accion.render() if accion is not None else None
        caja = None
        if dependiente:
            dependientes += 1
            caja = ("sin_accion" if accion is None else "correcta" if rend == esperada.render()
                    else "sorda" if rend == sorda.render() else "otra")
            cajas[caja] += 1
            if primer_dependiente is None:
                primer_dependiente = caja
        if traza is not None:
            with open(traza, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "http": 200, "step": obs.step, "actionable": obs.actionable,
                    "posterior": bool(posterior), "dependiente": bool(dependiente),
                    "caja": caja, "esperado": esperada.render(), "sordo": sorda.render(),
                    "ejecutado": rend, "correct": rend == esperada.render(),
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
        if accion is not None:
            actualiza(creencia, accion)
        env.apply(accion if accion is not None else NO_OP)
        ref.apply(ref.expected_action())
    return {**cajas, "dependientes": dependientes, "primer_dependiente": primer_dependiente,
            "score_dependientes": cajas["correcta"] / dependientes if dependientes else None,
            "truncadas": truncadas, "sin_accion_total": sin_accion_total, "pasos": pasos,
            "pasos_con_mundo_distinto": mundo_distinto,
            "entrada_efectiva": efectiva, "salida": salida,
            "parches_invalidos": getattr(rt, "invalid_patches", 0)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="claude-sonnet-5")
    p.add_argument("--runtimes", nargs="*", default=["skillstate", "react"])
    p.add_argument("--seeds", nargs="*", type=int, default=[0, 1])
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--max-tokens", type=int, default=600)
    p.add_argument("--thinking-budget", type=int, default=None)
    p.add_argument("--provider", default="auto",
                   choices=["auto", "api", "foundry", "gemini", "vertex"])
    args = p.parse_args()

    load_env()
    keep_system_awake()
    cliente = build_client(args.model, args.provider, args.max_tokens,
                           thinking_budget=args.thinking_budget)
    # Un agregado por proceso: dos procesos sobre el mismo JSON se pisarian.
    ruta = Path("results") / (f"diagnose_probeC_v2_{args.model}_{'-'.join(args.runtimes)}"
                              f"_s{'-'.join(map(str, args.seeds))}.json")
    ruta.parent.mkdir(exist_ok=True)
    hechos: dict = json.loads(ruta.read_text()) if ruta.exists() else {}

    for rt in args.runtimes:
        for seed in args.seeds:
            for rep in range(args.repeats):
                clave = f"{args.model}:{rt}:s{seed}:r{rep}:k{args.k}:mt{args.max_tokens}"
                if clave in hechos:
                    continue
                traza = Path("results") / (f"l2v2_{args.model}_{rt}_s{seed}_r{rep}"
                                           f"_k{args.k}_mt{args.max_tokens}.jsonl")
                d = episodio(cliente, seed, args.k, rt, traza=traza, condiciones={
                    "sonda": "L2", "version_sonda": VERSION_SONDA, "model": args.model,
                    "provider": cliente.provider, "runtime": rt, "seed": seed, "rep": rep,
                    "invalidation_k": args.k, "max_tokens": args.max_tokens,
                    "thinking_budget": args.thinking_budget})
                hechos[clave] = d
                ruta.write_text(json.dumps(hechos, indent=2))
                print(f"{clave}\n  dependientes={d['dependientes']} correcta={d['correcta']} "
                      f"sorda={d['sorda']} otra={d['otra']} sin_accion={d['sin_accion']}\n"
                      f"  truncadas={d['truncadas']}/{d['pasos']} "
                      f"parches_invalidos={d['parches_invalidos']}", flush=True)
    release()


if __name__ == "__main__":
    main()
