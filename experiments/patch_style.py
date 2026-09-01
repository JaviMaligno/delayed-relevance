"""Por que Sonnet no alcanza el techo de Haiku con el mismo campo en el esquema.

Hipotesis: Sonnet emite parches minimos (solo la clave que cambia) mientras Haiku
tiende a reemitir el estado, lo que le da auto-correccion. Con merge profundo las dos
estrategias son validas, pero la de Sonnet no re-sincroniza nunca: si el campo de la
cuarentena se pierde una vez, no hay recuperacion.

Mide, sobre la sonda A con esquema oraculo:
  - cuantas claves lleva cada parche;
  - cuantas veces se reemite el mapa completo de estanterias;
  - en que paso aparece `quarantined_shelves` y si sobrevive hasta el paso dependiente.

Lo ultimo es lo decisivo: no basta con guardar el hecho, hay que seguir teniendolo.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

from dr.config import load_env
from dr.envs.warehouse import Warehouse
from dr.keepawake import keep_system_awake, release
from dr.llm import AnthropicClient
from dr.runtimes.skillstate import SkillStateRuntime

CAMPO = "quarantined_shelves"


class RuntimeConRegistro(SkillStateRuntime):
    """Igual que SKILL.state pero anotando cada parche aplicado."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.registro: list[dict] = []

    def _merge(self, patch: dict) -> None:
        estanterias = patch.get("shelf_contents")
        self.registro.append(
            {
                "claves": sorted(patch),
                "n_estanterias_en_parche": len(estanterias) if isinstance(estanterias, dict) else 0,
                "n_estanterias_en_estado": len(self.state.get("shelf_contents") or {}),
                "toca_cuarentena": CAMPO in patch,
            }
        )
        super()._merge(patch)


def episodio(modelo: str, seed: int, k: int, max_tokens: int) -> dict:
    env = Warehouse(horizon=50, seed=seed, latent_k=k, oracle_schema=True)
    cliente = AnthropicClient(model=modelo, max_tokens=max_tokens)
    rt = RuntimeConRegistro(cliente, env.spec(), env.schema_fields())
    env.reset()
    acierto = None
    paso_primer_registro = None
    presente_en_dependiente = None
    while not env.done:
        esperada = env.expected_action()
        es_dependiente = env.step_index == env.dependent_step
        if es_dependiente:
            presente_en_dependiente = bool(rt.state.get(CAMPO))
        accion, _ = rt.act(env.observe())
        if es_dependiente:
            acierto = accion is not None and accion.render() == esperada.render()
        if paso_primer_registro is None and rt.state.get(CAMPO):
            paso_primer_registro = env.step_index
        env.apply(accion if accion is not None else esperada)

    parches = rt.registro
    reemisiones = sum(
        1 for p in parches
        if p["n_estanterias_en_parche"] >= max(1, p["n_estanterias_en_estado"])
    )
    con_estanterias = sum(1 for p in parches if p["n_estanterias_en_parche"] > 0)
    return {
        "acierto": bool(acierto),
        "claves_por_parche": sum(len(p["claves"]) for p in parches) / max(1, len(parches)),
        "reemite_estado_pct": 100 * reemisiones / max(1, con_estanterias),
        "paso_en_que_guarda_cuarentena": paso_primer_registro,
        "cuarentena_presente_al_usarla": presente_en_dependiente,
        "veces_que_toca_cuarentena": sum(1 for p in parches if p["toca_cuarentena"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=["claude-haiku-4-5", "claude-sonnet-5"])
    parser.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2])
    parser.add_argument("--k", type=int, default=40)
    parser.add_argument("--max-tokens", type=int, default=600)
    args = parser.parse_args()

    load_env()
    keep_system_awake()
    resumen: dict[str, list[dict]] = {}
    for modelo in args.models:
        resumen[modelo] = []
        for seed in args.seeds:
            r = episodio(modelo, seed, args.k, args.max_tokens)
            resumen[modelo].append(r)
            print(
                f"{modelo} seed={seed}: acierto={'OK' if r['acierto'] else 'X'} "
                f"claves/parche={r['claves_por_parche']:.2f} "
                f"reemite={r['reemite_estado_pct']:.0f}% "
                f"guarda_en={r['paso_en_que_guarda_cuarentena']} "
                f"presente_al_usarla={r['cuarentena_presente_al_usarla']}",
                flush=True,
            )

    print("\nRESUMEN")
    for modelo, filas in resumen.items():
        if not filas:
            continue
        n = len(filas)
        presente = sum(1 for f in filas if f["cuarentena_presente_al_usarla"])
        guardado = sum(1 for f in filas if f["paso_en_que_guarda_cuarentena"] is not None)
        print(
            f"{modelo:20} aciertos {sum(f['acierto'] for f in filas)}/{n} | "
            f"llega a guardar la cuarentena {guardado}/{n} | "
            f"la conserva hasta usarla {presente}/{n} | "
            f"claves/parche {sum(f['claves_por_parche'] for f in filas)/n:.2f} | "
            f"reemite estado {sum(f['reemite_estado_pct'] for f in filas)/n:.0f}%"
        )
    print("\nSi guarda pero no conserva, el problema es la persistencia del parche,")
    print("no la decision de guardar. Son dos fallos distintos con arreglos distintos.")
    release()


if __name__ == "__main__":
    main()
