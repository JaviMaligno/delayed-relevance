"""Separa, en los fallos de un brazo con estado explicito, que parte es del ESTADO.

Reproduce el entorno real con las acciones que el modelo ejecuto y, paso a paso,
compara el inventario que el modelo cree con el que hay. Cada fallo cae en una de tres
clases, y solo la primera es atribuible al estado:

- **estado_causa**: el inventario creido difiere del real, el creido prescribe OTRA
  accion que el real, y el modelo ejecuto exactamente la que prescribe el creido.
- **estado_discrepante_sin_efecto**: habia discrepancia, pero o bien ambos inventarios
  prescriben la misma accion, o bien el modelo no siguio ninguno de los dos. Que el
  estado estuviera mal no explica ese fallo.
- **estado_correcto**: el inventario creido coincidia con el real.

El origen de cada episodio con discrepancia es el primer paso en que la creencia se
aparto de la realidad, con si la accion de ese paso era correcta: un parche mal escrito
con la accion bien es el caso que el estado explicito no protege.

Revision adversarial 3 (hallazgos 2, 3, 5 y 6): se comparan unidades ademas de SKU y
lote; un valor que es solo el SKU se lee como estanteria ocupada por ese SKU, no como
vacia; y el estado de Stateful se reconstruye con el parser de la version que grabo la
traza, porque reconstruirlo con uno posterior inventa un estado que el modelo nunca vio.
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

_DECODER = json.JSONDecoder()


def _parche_stateful_v1(texto: str):
    m = re.search(r"StateUpdate:\s*(\{.*?\})", texto, re.DOTALL)
    try:
        return json.loads(m.group(1)) if m else None
    except json.JSONDecodeError:
        return None


def _parche_stateful_v2(texto: str):
    m = re.search(r"StateUpdate:\s*(?=\{)", texto)
    try:
        return _DECODER.raw_decode(texto, m.end())[0] if m else None
    except json.JSONDecodeError:
        return None


def _aplicar_stateful(version: int, estado: dict, texto: str, campos: set) -> dict:
    if version >= 3:
        rt = StatefulRuntime(client=None, spec="", schema_fields=sorted(campos))
        rt.state = estado
        rt._apply_state_update(texto)
        return rt.state
    parche = (_parche_stateful_v1 if version == 1 else _parche_stateful_v2)(texto)
    if isinstance(parche, dict):
        _merge_into(estado, {k: v for k, v in parche.items() if k in campos}, deep=True)
    return estado


def _unidades(valor):
    """Unidades tal como las escribio el modelo: un numero en texto cuenta como numero, y
    un decimal no se redondea -- 14.9 no son 14 unidades."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return int(numero) if numero.is_integer() else numero


def _creencia(estado: dict) -> dict[int, tuple | None]:
    """Inventario creido. Un valor que es solo el SKU significa `ocupada por ese SKU`
    con unidades y lote sin especificar, no `vacia`."""
    salida: dict[int, tuple | None] = {}
    for clave, valor in (estado.get("shelf_contents") or {}).items():
        try:
            indice = int(clave)
        except (TypeError, ValueError):
            continue
        if isinstance(valor, dict):
            salida[indice] = (str(valor.get("sku")), _unidades(valor.get("units")),
                              str(valor.get("lot")) if valor.get("lot") is not None else None)
        elif isinstance(valor, str) and valor:
            salida[indice] = (valor, None, None)
        else:
            salida[indice] = None
    return salida


def _realidad(env: Warehouse) -> dict[int, tuple | None]:
    return {i: (c[0], c[1], c[2]) if c else None for i, c in env.shelves.items()}


def _coincide_estante(creido, real) -> bool:
    if creido is None or real is None:
        return creido is real
    # Los campos que el modelo no especifico no cuentan como discrepancia.
    return all(c is None or c == r for c, r in zip(creido, real))


def _coincide(creencia, realidad) -> bool:
    return all(_coincide_estante(creencia.get(i), realidad[i]) for i in realidad)


def _prescrita_por(env: Warehouse, creencia: dict) -> str:
    """Accion que prescribe el ground truth si el almacen fuera el que cree el modelo."""
    reales = env.shelves
    env.shelves = {i: (creencia.get(i) if creencia.get(i) is None
                       else (creencia[i][0], creencia[i][1] or 0, creencia[i][2] or ""))
                   for i in reales}
    try:
        return env.expected_action().render()
    finally:
        env.shelves = reales


def adjudicar(fichero: Path, por_defecto: dict | None = None) -> dict:
    filas = [json.loads(l) for l in fichero.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    cabecera = next((f["condiciones"] for f in filas if f.get("kind") == "run_header"), None)
    if cabecera is None:
        if por_defecto is None:
            raise SystemExit(f"{fichero.name}: sin cabecera de condiciones; pasa "
                             "--condiciones con las de su corrida en vez de suponerlas")
        cabecera = dict(por_defecto)
        cabecera.setdefault("seed", int(re.search(r"_s(\d+)_", fichero.name).group(1)))
        cabecera.setdefault("runtime", re.search(r"_(react|memory|stateful|skillstate)_",
                                                 fichero.name).group(1))
    pasos = [f for f in filas if f.get("kind") != "run_header"]
    env = Warehouse(horizon=len(pasos), seed=cabecera["seed"],
                    apendice_b=cabecera.get("apendice_b", False),
                    sin_telemetria=cabecera.get("sin_telemetria", False),
                    ruido=cabecera.get("ruido", 0))
    env.reset()
    campos = set(env.schema_fields())
    stateful = cabecera.get("runtime") == "stateful"
    version = cabecera.get("stateful_parser") or 1
    estado: dict = {}
    origen = None
    clases = {"estado_causa": 0, "estado_discrepante_sin_efecto": 0, "estado_correcto": 0}
    for paso in pasos:
        env.observe()
        creencia, realidad = _creencia(estado), _realidad(env)
        bien_antes = _coincide(creencia, realidad)
        if paso.get("actionable") and not paso.get("correct"):
            if bien_antes:
                clases["estado_correcto"] += 1
            else:
                segun_creencia = _prescrita_por(env, creencia)
                if (segun_creencia != env.expected_action().render()
                        and paso.get("ejecutado") == segun_creencia):
                    clases["estado_causa"] += 1
                else:
                    clases["estado_discrepante_sin_efecto"] += 1
        if stateful:
            estado = _aplicar_stateful(version, estado, paso["raw"]["respuestas"][-1], campos)
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
    p.add_argument("--condiciones", default=None,
                   help="JSON con las condiciones de trazas SIN cabecera, p. ej. "
                        '\'{"apendice_b": true, "sin_telemetria": true}\'. Sin esto, una '
                        "traza sin cabecera es un error: no se suponen condiciones.")
    args = p.parse_args()
    por_defecto = json.loads(args.condiciones) if args.condiciones else None
    total = {"estado_causa": 0, "estado_discrepante_sin_efecto": 0, "estado_correcto": 0}
    origenes = {"parche_mal_con_accion_bien": 0, "accion_mal": 0}
    episodios = con_efecto = 0
    for f in sorted(Path().glob(args.patron)):
        r = adjudicar(f, por_defecto)
        episodios += 1
        for k, v in r["clases"].items():
            total[k] += v
        con_efecto += r["clases"]["estado_causa"] > 0
        o = r["origen"]
        if o:
            origenes["parche_mal_con_accion_bien" if o["accion_correcta"] else "accion_mal"] += 1
        if sum(r["clases"].values()) or o:
            print(f"{r['fichero']}: {r['clases']}  origen="
                  f"{o and (o['paso'], 'accion bien' if o['accion_correcta'] else 'accion mal', o['ejecutado'])}")
    print(f"\nepisodios: {episodios}")
    print("fallos:", total)
    print("episodios cuya creencia se aparto de la realidad, por su origen:", origenes)
    print("episodios con al menos un fallo causado por el estado:", con_efecto)


if __name__ == "__main__":
    main()
