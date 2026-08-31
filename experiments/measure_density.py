"""Mide el tamano de prompt de cada runtime SIN llamar a la API.

Sustituye el modelo por un oraculo que siempre acierta y responde en el formato que
espera cada runtime. Lo unico que interesa aqui es cuanto contexto ve el modelo en
cada paso, y eso no depende de que el modelo acierte.

Existe porque la primera calibracion se gasto una rejilla entera para descubrir que
nuestro entorno era tres veces mas ligero que el del paper. Esa comprobacion es
gratis y va antes.
"""
from __future__ import annotations

import argparse
import json

from dr.envs.warehouse import Warehouse
from dr.llm import Completion
from dr.runtimes.memory import MemoryRuntime
from dr.runtimes.react import ReActRuntime
from dr.runtimes.skillstate import SkillStateRuntime
from dr.runtimes.stateful import StatefulRuntime

# Calibrado contra la corrida real de T=10 con react, stateful y skillstate: el texto
# del entorno lleva muchos identificadores y numeros, que tokenizan peor que la prosa.
# Se excluye memory del ajuste: su runtime real acumula resumenes que el oraculo no
# reproduce, asi que su ratio no mide la tokenizacion sino esa diferencia.
CHARS_PER_TOKEN = 3.48

# Prompt medio por invocacion en la Tabla 1 del paper (Gemini-3-Flash).
PAPER_AVG_PROMPT = {
    "react": {10: 3249, 25: 6052, 50: 11931, 100: 36362},
    "memory": {10: 3300, 25: 6357, 50: 7582, 100: 29607},
    "stateful": {10: 3430, 25: 5858, 50: 11594, 100: 31354},
    "skillstate": {10: 1775, 25: 1736, 50: 1773, 100: 1905},
}


class OracleClient:
    """Devuelve siempre la accion correcta, en el formato de cada runtime.

    El razonamiento se rellena hasta `response_tokens`. Esto NO es decorativo: en los
    runtimes con historia la respuesta del modelo se acumula en el transcript, asi
    que su longitud pesa tanto como la de las observaciones. La primera version de
    este script respondia en dos lineas y por eso subestimo la densidad real casi a
    la mitad, dando por calibrado un entorno que no lo estaba.
    """

    def __init__(self, shape: str, response_tokens: int) -> None:
        self.shape = shape
        self.prompt_chars: list[int] = []
        self.next_action = "Wait({})"
        self.next_patch: dict = {}
        self.filler = "The event is parsed and the relevant fields are identified. " * max(
            1, response_tokens // 12
        )

    def complete(self, system: str, user: str) -> Completion:
        self.prompt_chars.append(len(system) + len(user))
        if self.shape == "plain":
            text = f"{self.filler}\nAction: {self.next_action}"
        elif self.shape == "stateupdate":
            text = (
                f"{self.filler}\n"
                f"StateUpdate: {json.dumps(self.next_patch)}\n"
                f"Action: {self.next_action}"
            )
        else:
            body = json.dumps({"state_patch": self.next_patch, "action": self.next_action})
            text = f"{self.filler}\n```json\n{body}\n```"
        return Completion(text=text, prompt_tokens=0, output_tokens=len(text) // 4)


def run(name: str, horizon: int, seed: int, response_tokens: int) -> float:
    env = Warehouse(horizon=horizon, seed=seed)
    shape = {"react": "plain", "memory": "plain", "stateful": "stateupdate"}.get(name, "json")
    client = OracleClient(shape, response_tokens)
    runtime = {
        "react": lambda: ReActRuntime(client, env.spec()),
        "memory": lambda: MemoryRuntime(client, env.spec()),
        "stateful": lambda: StatefulRuntime(client, env.spec(), env.schema_fields()),
        "skillstate": lambda: SkillStateRuntime(client, env.spec(), env.schema_fields()),
    }[name]()
    env.reset()
    while not env.done:
        expected = env.expected_action()
        client.next_action = expected.render()
        shelves = {
            str(i): {"sku": c[0], "units": c[1], "lot": c[2]}
            for i, c in env.shelves.items()
            if c is not None
        }
        client.next_patch = {"shelf_contents": shelves, "last_event": env.observe().text[:60]}
        runtime.act(env.observe())
        env.apply(expected)
    return sum(client.prompt_chars) / len(client.prompt_chars) / CHARS_PER_TOKEN


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizons", nargs="*", type=int, default=[10, 25, 50, 100])
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--response-tokens", type=int, default=250,
                        help="Longitud tipica de la respuesta del modelo. Pesa en los "
                             "brazos con historia porque se acumula en el transcript.")
    args = parser.parse_args()

    print(f"{'runtime':11} " + " ".join(f"{'T=' + str(h):>18}" for h in args.horizons))
    print(f"{'':11} " + " ".join(f"{'nuestro/ellos':>18}" for _ in args.horizons))
    for name in ["react", "memory", "stateful", "skillstate"]:
        cells = []
        for h in args.horizons:
            ours = run(name, h, args.seed, args.response_tokens)
            theirs = PAPER_AVG_PROMPT[name].get(h)
            ratio = f"{ours / theirs:.2f}x" if theirs else "-"
            cells.append(f"{ours:.0f}/{theirs or '-'} {ratio}".rjust(18))
        print(f"{name:11} " + " ".join(cells))
    print("\nObjetivo: ratio cerca de 1.00. Estimacion a 4 caracteres por token.")


if __name__ == "__main__":
    main()
