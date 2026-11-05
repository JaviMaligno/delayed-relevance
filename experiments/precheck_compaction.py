"""Comprobaciones gratis del experimento de compactacion: sin llamar a ningun modelo.

1. Para cada sonda y seed: en que paso cae el aviso, en cuales las compactaciones y en
   cuales los pasos dependientes, y si al menos una compactacion cae entre el aviso y
   un paso dependiente. Si en alguna seed no cae, la sonda no prueba la compactacion
   ahi: se reporta con los numeros y NO se mueve la cadencia desde aqui.
2. Suelos deterministas, medidos con el MISMO `episodio` del corredor:
   - **sordo**: agente perfecto que nunca aplica el aviso (sin compactar);
   - **olvidadizo**: agente perfecto con lo que tiene en contexto que **nunca
     consulta**. Es el suelo de `fresh_lookup`: en cada compactacion olvida todo lo
     anterior (ocupacion de estanterias y avisos) y sigue desde ahi;
   - **perfecto**: la politica correcta (techo, sanity check: 1.0 en todo).
   Si el olvidadizo se acerca al techo, la sonda no discrimina `fresh_lookup`.

Uso: PYTHONPATH=src python experiments/precheck_compaction.py
"""
from __future__ import annotations

from dr.envs.warehouse import SHELF_COUNT, event_field
from dr.runtimes.compaction import CADENCIA
from dr.types import Action

try:  # como script (experiments/ en sys.path) o importado desde los tests
    from run_compaction import HORIZONTE, construir_env, episodio
except ImportError:
    from experiments.run_compaction import HORIZONTE, construir_env, episodio

COMPACTACIONES = list(range(CADENCIA, HORIZONTE, CADENCIA))


class Politica:
    """Agente determinista que lleva su propia creencia de la ocupacion.

    `olvida`: vacia la creencia (y los avisos que conocia) en cada compactacion.
    `oye_avisos`: aplica la correccion de la sonda C y la cuarentena de la sonda A
    mientras el aviso siga en su contexto."""

    def __init__(self, olvida: bool, oye_avisos: bool) -> None:
        self.olvida = olvida
        self.oye_avisos = oye_avisos
        self.creencia: dict[int, str | None] = {i: None for i in range(SHELF_COUNT)}
        self.cuarentena: set[int] = set()
        self.pasos = 0
        self.compactaciones: list[int] = []

    def act(self, obs):
        if self.olvida and self.pasos and self.pasos % CADENCIA == 0:
            self.creencia = {i: None for i in range(SHELF_COUNT)}
            self.cuarentena = set()
            self.compactaciones.append(self.pasos)
        self.pasos += 1
        texto = obs.text
        if self.oye_avisos and "correction_notice" in texto:
            self.creencia[int(event_field(texto, "shelf"))] = None
        if self.oye_avisos and "facility_notice" in texto and "status=quarantined" in texto:
            self.cuarentena.add(int(event_field(texto, "shelf")))
        accion = self._decidir(obs)
        if accion.name == "Store":
            self.creencia[accion.args["shelf"]] = accion.args["sku"]
        elif accion.name == "Ship":
            self.creencia[accion.args["shelf"]] = None
        return accion, []

    def _decidir(self, obs) -> Action:
        if not obs.actionable:
            return Action(name="Wait")
        sku = event_field(obs.text, "sku") or ""
        if "inbound_pallet" in obs.text:
            libre = next(i for i in range(SHELF_COUNT)
                         if self.creencia[i] is None and i not in self.cuarentena)
            return Action(name="Store", args={"shelf": libre, "sku": sku,
                                              "units": int(event_field(obs.text, "units") or 0),
                                              "lot": event_field(obs.text, "lot") or ""})
        for i in range(SHELF_COUNT):
            if self.creencia[i] == sku:
                return Action(name="Ship", args={"shelf": i, "sku": sku})
        return Action(name="Wait")


class Perfecto:
    """La accion correcta en cada paso, leida del propio entorno."""

    def __init__(self, env) -> None:
        self.env = env

    def act(self, obs):
        return self.env.expected_action(), []


def geometria(sonda: str, seed: int, k: int) -> dict:
    """Pasos del aviso y dependientes en la trayectoria del agente perfecto."""
    env = construir_env(sonda, seed, k)
    d = episodio(env, Perfecto(env), sonda)
    aviso = d["paso_aviso"]
    if sonda == "C":
        dependientes = d["pasos_dependientes"]
    else:
        dependientes = [env.dependent_step]
    entre = {dep: [c for c in COMPACTACIONES if aviso < c <= dep] for dep in dependientes}
    return {"aviso": aviso, "dependientes": dependientes, "entre": entre,
            "dep_sin_compactacion": [dep for dep, cs in entre.items() if not cs]}


def suelos(sonda: str, seed: int, k: int) -> dict:
    fila = {}
    for nombre, rt_de in (("perfecto", lambda e: Perfecto(e)),
                          ("sordo", lambda e: Politica(olvida=False, oye_avisos=False)),
                          ("olvidadizo", lambda e: Politica(olvida=True, oye_avisos=True))):
        env = construir_env(sonda, seed, k)
        d = episodio(env, rt_de(env), sonda)
        fila[nombre] = d
    return fila


def main() -> None:
    print(f"Compactaciones (antes de mostrar el paso): {COMPACTACIONES}, T={HORIZONTE}\n")
    problemas = []
    for sonda, k, seeds in (("C", 14, [17, 6, 10]), ("A", 40, [0, 3, 6])):
        print(f"=== Sonda {sonda} (k={k}) ===")
        for seed in seeds:
            g = geometria(sonda, seed, k)
            s = suelos(sonda, seed, k)
            hay = any(g["entre"].values())
            print(f"seed {seed}: aviso en el paso {g['aviso']}; "
                  f"pasos dependientes (trayectoria perfecta) {g['dependientes']}")
            for dep, cs in g["entre"].items():
                print(f"    dependiente {dep}: compactaciones entre aviso y paso -> {cs or 'NINGUNA'}")
            print(f"    al menos una compactacion entre aviso y dependientes: {'SI' if hay else 'NO'}"
                  + (f" (sin compactacion de por medio: {g['dep_sin_compactacion']})"
                     if g["dep_sin_compactacion"] else ""))
            for nombre, d in s.items():
                print(f"    {nombre:10} score={d['score']:.3f}  metrica={d['aciertos']}/{d['dependientes']}"
                      + (f"  dependientes en su trayectoria={d['pasos_dependientes']}"
                         if sonda == "C" else f"  materializa={d['materializa']}"))
            if sonda == "C":
                # Los pasos dependientes se definen sobre la trayectoria REAL: tras
                # acertar el primero, la creencia del sordo vuelve a coincidir con la
                # verdad y no hay mas. Los siguientes solo existen si el agente fallo.
                cascada = s["sordo"]["pasos_dependientes"]
                tras = [dep for dep in cascada if any(g["aviso"] < c <= dep for c in COMPACTACIONES)]
                print(f"    en la trayectoria del sordo (cascada): {len(tras)} de {len(cascada)} "
                      f"dependientes tienen una compactacion entre el aviso y el paso: {tras}")
            if not hay:
                problemas.append(f"sonda {sonda} seed {seed}")
        print()
    if problemas:
        print("ATENCION: sin compactacion entre aviso y dependientes en: " + ", ".join(problemas))
    else:
        print("Todas las seeds tienen al menos una compactacion entre el aviso y un paso dependiente.")


if __name__ == "__main__":
    main()
