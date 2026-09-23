"""Separa, en los fallos de un brazo con estado explicito, que parte es del ESTADO.

Reproduce el entorno real con las acciones que el modelo ejecuto y, paso a paso,
compara el `shelf_contents` que el modelo cree con el que hay. Asi cada fallo cae en
una de dos clases:

- **estado heredado**: el modelo ya creia algo falso antes de actuar. El origen es el
  primer paso en que su creencia se aparto de la realidad, y ahi se mira si la accion
  de ese paso era correcta -- un parche mal copiado con la accion bien es el caso que
  el estado explicito no protege, porque el error entra por la propia escritura.
- **accion con estado correcto**: el estado era bueno y aun asi eligio mal.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dr.envs.warehouse import Warehouse
from dr.runner import NO_OP
from dr.runtimes.skillstate import SkillStateRuntime, _merge_into
from dr.runtimes.stateful import StatefulRuntime
from dr.types import Action


def _creencia(estado: dict) -> dict[int, tuple[str, str] | None]:
    salida = {}
    for clave, valor in (estado.get("shelf_contents") or {}).items():
        try:
            indice = int(clave)
        except (TypeError, ValueError):
            continue
        salida[indice] = ((str(valor.get("sku")), str(valor.get("lot")))
                          if isinstance(valor, dict) else None)
    return salida


def _realidad(env: Warehouse) -> dict[int, tuple[str, str] | None]:
    return {i: (c[0], c[2]) if c else None for i, c in env.shelves.items()}


def _coincide(creencia, realidad) -> bool:
    return all(creencia.get(i) == realidad[i] for i in realidad)


def adjudicar(fichero: Path) -> dict:
    filas = [json.loads(l) for l in fichero.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    cabecera = next((f["condiciones"] for f in filas if f.get("kind") == "run_header"), {})
    pasos = [f for f in filas if f.get("kind") != "run_header"]
    env = Warehouse(horizon=len(pasos), seed=cabecera["seed"],
                    apendice_b=cabecera.get("apendice_b", False),
                    sin_telemetria=cabecera.get("sin_telemetria", False),
                    ruido=cabecera.get("ruido", 0))
    env.reset()
    campos = set(env.schema_fields())
    estado: dict = {}
    # Stateful escribe `StateUpdate: {...}` y no reintenta; se aplica con su propio
    # parser para reproducir exactamente el estado que vio el modelo.
    stateful = (StatefulRuntime(client=None, spec="", schema_fields=sorted(campos))
                if cabecera.get("runtime") == "stateful" else None)
    origen = None
    clases = {"estado_heredado": 0, "accion_con_estado_correcto": 0}
    for paso in pasos:
        env.observe()
        bien_antes = _coincide(_creencia(estado), _realidad(env))
        if paso.get("actionable") and not paso.get("correct"):
            clases["estado_heredado" if not bien_antes else "accion_con_estado_correcto"] += 1
        if stateful is not None:
            stateful._apply_state_update(paso["raw"]["respuestas"][-1])
            estado = stateful.state
        else:
            for respuesta in paso["raw"]["respuestas"]:
                leido = SkillStateRuntime._parse(respuesta)
                if leido is not None and all(k in campos for k in leido[0]):
                    _merge_into(estado, leido[0], deep=True)
                    break
        accion = Action.parse(paso["ejecutado"]) if paso.get("ejecutado") else None
        env.apply(accion if accion is not None else NO_OP)
        if origen is None and bien_antes and not _coincide(_creencia(estado), _realidad(env)):
            origen = {"paso": paso["step"], "accion_correcta": paso.get("correct"),
                      "esperado": paso.get("esperado"), "ejecutado": paso.get("ejecutado")}
    return {"fichero": fichero.name, "clases": clases, "origen": origen}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("patron", help="glob de trazas, p. ej. 'results/adj_T200_*_skillstate_*_h?.jsonl'")
    args = p.parse_args()
    total = {"estado_heredado": 0, "accion_con_estado_correcto": 0}
    origenes = {"parche_mal_con_accion_bien": 0, "accion_mal": 0}
    for f in sorted(Path().glob(args.patron)):
        r = adjudicar(f)
        for k, v in r["clases"].items():
            total[k] += v
        o = r["origen"]
        if o:
            origenes["parche_mal_con_accion_bien" if o["accion_correcta"] else "accion_mal"] += 1
        if sum(r["clases"].values()) or o:
            print(f"{r['fichero']}: {r['clases']}  origen={o and (o['paso'], 'accion bien' if o['accion_correcta'] else 'accion mal', o['ejecutado'])}")
    print("\nfallos:", total)
    print("episodios con estado corrompido, por su origen:", origenes)


if __name__ == "__main__":
    main()
