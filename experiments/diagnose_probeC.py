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
from dr.types import Action

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


def episodio(cliente, seed: int, k: int, runtime: str) -> dict:
    env = Warehouse(horizon=50, seed=seed, invalidation_k=k)
    rt = RUNTIMES[runtime](cliente, env)
    env.reset()
    # La creencia se congela ANTES de que el aviso vacie la estanteria y a partir de
    # ahi solo la mueven las acciones del propio agente: es su mundo si no oyo nada.
    creencia = dict(env.shelves)
    cajas = {"correcta": 0, "sorda": 0, "otra": 0}
    truncadas = sin_accion = pasos = 0
    efectiva = salida = 0.0
    while not env.done:
        obs = env.observe()
        esperada = env.expected_action()
        sorda = accion_sorda(obs, creencia)
        accion, completions = rt.act(obs)
        pasos += 1
        truncadas += sum(1 for c in completions if c.truncated)
        efectiva += sum(c.prompt_tokens + c.cache_read * 0.10
                        + c.cache_write * 1.25 for c in completions)
        salida += sum(c.output_tokens for c in completions)
        sin_accion += accion is None
        posterior = (env.invalidation_from is not None
                     and env.step_index > env.invalidation_from)
        if posterior and obs.actionable:
            rend = accion.render() if accion is not None else None
            if rend == esperada.render():
                cajas["correcta"] += 1
            elif rend == sorda.render():
                cajas["sorda"] += 1
            else:
                cajas["otra"] += 1
        actualiza(creencia, accion if accion is not None else esperada)
        env.apply(accion if accion is not None else esperada)
    n = sum(cajas.values())
    return {**cajas, "n_posteriores": n,
            "score_posterior": cajas["correcta"] / n if n else 0.0,
            "truncadas": truncadas, "sin_accion": sin_accion, "pasos": pasos,
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
    p.add_argument("--provider", default="auto",
                   choices=["auto", "api", "foundry", "gemini", "vertex"])
    args = p.parse_args()

    load_env()
    keep_system_awake()
    cliente = build_client(args.model, args.provider, args.max_tokens)
    ruta = Path("results") / "diagnose_probeC.json"
    ruta.parent.mkdir(exist_ok=True)
    hechos: dict = json.loads(ruta.read_text()) if ruta.exists() else {}

    for rt in args.runtimes:
        for seed in args.seeds:
            for rep in range(args.repeats):
                clave = f"{args.model}:{rt}:s{seed}:r{rep}:k{args.k}:mt{args.max_tokens}"
                if clave in hechos:
                    continue
                d = episodio(cliente, seed, args.k, rt)
                hechos[clave] = d
                ruta.write_text(json.dumps(hechos, indent=2))
                print(f"{clave}\n  correcta={d['correcta']} sorda={d['sorda']} "
                      f"otra={d['otra']} de {d['n_posteriores']}  "
                      f"score={d['score_posterior']:.3f}\n"
                      f"  truncadas={d['truncadas']}/{d['pasos']} "
                      f"sin_accion={d['sin_accion']} "
                      f"parches_invalidos={d['parches_invalidos']}", flush=True)
    release()


if __name__ == "__main__":
    main()
