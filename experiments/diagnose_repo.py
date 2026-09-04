"""Comprobar si las celdas de Repo miden la tarea o miden un fallo del corredor.

El diagnostico de la sonda C encontro que el brazo de ReAct en Sonnet perdia hasta 19
de 50 pasos por truncamiento —respuesta cortada antes de la linea de accion— y que el
de SKILL.state acumulaba hasta 18 parches invalidos. Un score bajo por esos motivos no
dice nada del metodo. Antes de publicar la inversion de Repo hay que descartar lo mismo
alli.

Registra por episodio: truncamientos, pasos sin accion, parches invalidos y, aparte, el
acierto en los pasos PORTANTES (las solicitudes de merge cuyo CI fue invalidado por un
merge anterior) frente al resto. El suelo de una politica ciega en Repo es 0.853, asi
que sin esa separacion un score de 0.876 es ilegible.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dr.config import load_env
from dr.envs.repo import Repo
from dr.keepawake import keep_system_awake, release
from dr.llm import AnthropicClient
from dr.runtimes.react import ReActRuntime
from dr.runtimes.skillstate import SkillStateRuntime

RUNTIMES = {
    "skillstate": lambda c, e: SkillStateRuntime(c, e.spec(), e.schema_fields()),
    "react": lambda c, e: ReActRuntime(c, e.spec()),
}


def episodio(cliente, seed: int, runtime: str) -> dict:
    env = Repo(horizon=50, seed=seed)
    rt = RUNTIMES[runtime](cliente, env)
    env.reset()
    portante_ok = portante_n = resto_ok = resto_n = 0
    truncadas = sin_accion = 0
    efectiva = salida = 0.0
    while not env.done:
        obs = env.observe()
        esperada = env.expected_action()
        # Portante: se pide integrar una PR y la respuesta correcta NO es Merge, es
        # decir, su CI verde fue invalidado por un merge anterior sin aviso.
        portante = "solicitud_merge" in obs.text and esperada.name != "Merge"
        accion, completions = rt.act(obs)
        truncadas += sum(1 for c in completions if c.truncated)
        efectiva += sum(c.prompt_tokens + c.cache_read * 0.10
                        + c.cache_write * 1.25 for c in completions)
        salida += sum(c.output_tokens for c in completions)
        sin_accion += accion is None
        correcta = accion is not None and accion.render() == esperada.render()
        if obs.actionable:
            if portante:
                portante_n += 1
                portante_ok += correcta
            else:
                resto_n += 1
                resto_ok += correcta
        env.apply(accion if accion is not None else esperada)
    n = portante_n + resto_n
    return {"score": (portante_ok + resto_ok) / n if n else 0.0,
            "portantes": f"{portante_ok}/{portante_n}",
            "resto": f"{resto_ok}/{resto_n}",
            "truncadas": truncadas, "sin_accion": sin_accion,
            "entrada_efectiva": efectiva, "salida": salida,
            "parches_invalidos": getattr(rt, "invalid_patches", 0)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="claude-sonnet-5")
    p.add_argument("--runtimes", nargs="*", default=["skillstate"])
    p.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2])
    p.add_argument("--max-tokens", type=int, default=600)
    args = p.parse_args()

    load_env()
    keep_system_awake()
    cliente = AnthropicClient(model=args.model, max_tokens=args.max_tokens)
    ruta = Path("results") / "diagnose_repo.json"
    ruta.parent.mkdir(exist_ok=True)
    hechos: dict = json.loads(ruta.read_text()) if ruta.exists() else {}
    for rt in args.runtimes:
        for seed in args.seeds:
            clave = f"{args.model}:{rt}:s{seed}:mt{args.max_tokens}"
            if clave in hechos:
                continue
            d = episodio(cliente, seed, rt)
            hechos[clave] = d
            ruta.write_text(json.dumps(hechos, indent=2))
            print(f"{clave}\n  score={d['score']:.3f}  portantes={d['portantes']} "
                  f"resto={d['resto']}\n  truncadas={d['truncadas']} "
                  f"sin_accion={d['sin_accion']} parches_invalidos={d['parches_invalidos']}",
                  flush=True)
    release()


if __name__ == "__main__":
    main()
