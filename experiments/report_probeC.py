"""Sonda C agregada por MECANISMO, no por score.

El score del tramo posterior mezcla tres sucesos distintos: no aplicar la correccion
(el fallo que la sonda quiere medir), fallar por otra razon, y no emitir accion por
truncamiento o por parche invalido. Solo el primero dice algo del metodo.

La unidad de cuenta es el PASO DEPENDIENTE: cada paso posterior al aviso cuya accion
correcta cambia por haberlo aplicado. Un episodio con 11 pasos dependientes aporta 11
observaciones, no una. Los episodios con truncamiento por encima del umbral se
excluyen y se declaran: en ellos el brazo no llego a decidir.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

UMBRAL_TRUNCAMIENTO = 3


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--umbral", type=int, default=UMBRAL_TRUNCAMIENTO)
    args = p.parse_args()

    datos = json.loads((Path("results") / "diagnose_probeC.json").read_text())
    filas: dict[tuple[str, str], dict] = {}
    excluidos: list[str] = []
    for clave, d in sorted(datos.items()):
        modelo, runtime = clave.split(":")[0], clave.split(":")[1]
        if d["truncadas"] > args.umbral:
            excluidos.append(f"{clave} ({d['truncadas']} truncadas de {d['pasos']})")
            continue
        f = filas.setdefault((modelo, runtime),
                             {"sorda": 0, "dep": 0, "otra": 0, "post": 0,
                              "sin_accion": 0, "parches": 0, "eps": 0})
        # Pasos dependientes de este episodio = los que el agente sordo fallaria.
        # Se reconstruyen como sordas + las que acerto de entre ellas; como no se
        # distingue cual acerto, se usa el suelo teorico del episodio, que es
        # exactamente el numero de sordas que cometeria un agente perfecto sordo.
        f["sorda"] += d["sorda"]
        f["otra"] += d["otra"]
        f["post"] += d["n_posteriores"]
        f["sin_accion"] += d["sin_accion"]
        f["parches"] += d["parches_invalidos"]
        f["eps"] += 1

    # Los pasos dependientes por seed son una propiedad del entorno, no del brazo.
    from dr.envs.warehouse import SHELF_COUNT, Warehouse, event_field
    from dr.types import Action

    def dependientes(seed: int, k: int = 10) -> int:
        env = Warehouse(horizon=50, seed=seed, invalidation_k=k); env.reset()
        cre = dict(env.shelves); fallos = 0
        while not env.done:
            obs, esp = env.observe(), env.expected_action()
            if not obs.actionable:
                acc = Action(name="Wait")
            elif "inbound_pallet" in obs.text:
                libre = next(i for i in range(SHELF_COUNT) if cre[i] is None)
                acc = Action(name="Store", args={"shelf": libre,
                      "sku": event_field(obs.text, "sku") or "",
                      "units": int(event_field(obs.text, "units") or 0),
                      "lot": event_field(obs.text, "lot") or ""})
            else:
                sku = event_field(obs.text, "sku") or ""
                s = next((i for i in range(SHELF_COUNT) if cre[i] and cre[i][0] == sku), None)
                acc = Action(name="Wait") if s is None else Action(name="Ship", args={"shelf": s, "sku": sku})
            if (env.invalidation_from is not None and env.step_index > env.invalidation_from
                    and obs.actionable and acc.render() != esp.render()):
                fallos += 1
            if acc.name == "Store": cre[acc.args["shelf"]] = (acc.args["sku"], 0, "")
            elif acc.name == "Ship": cre[acc.args["shelf"]] = None
            env.apply(acc)
        return fallos

    for clave, d in sorted(datos.items()):
        if d["truncadas"] > args.umbral:
            continue
        modelo, runtime = clave.split(":")[0], clave.split(":")[1]
        # ":s" tambien casa con ":skillstate": hay que ir por posicion.
        seed = int(clave.split(":")[2][1:])
        filas[(modelo, runtime)]["dep"] += dependientes(seed)

    print("SONDA C — el fallo que la sonda mide, contado sobre PASOS DEPENDIENTES\n")
    print(f"{'modelo':18} {'runtime':11} {'aplica la correccion':>22} {'otros fallos':>13} "
          f"{'sin accion':>11} {'parches inv.':>13} {'eps':>4}")
    for (modelo, runtime), f in sorted(filas.items()):
        aciertos = f["dep"] - f["sorda"]
        pct = 100 * aciertos / f["dep"] if f["dep"] else 0
        print(f"{modelo:18} {runtime:11} {aciertos:9}/{f['dep']:<3} ({pct:5.1f}%) "
              f"{f['otra']:13} {f['sin_accion']:11} {f['parches']:13} {f['eps']:4}")
    if excluidos:
        print(f"\nExcluidos por truncamiento (> {args.umbral} de 50 pasos): {len(excluidos)}")
        for e in excluidos:
            print(f"  {e}")
        print("En esos episodios el brazo no llego a emitir accion; contarlos mediria")
        print("presupuesto de salida, no memoria.")


if __name__ == "__main__":
    main()
