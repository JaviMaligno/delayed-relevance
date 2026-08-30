from __future__ import annotations

import random

from dr.types import Action, Observation

SKUS = [f"SKU-{chr(ord('A') + i)}" for i in range(12)]
SHELF_COUNT = 500


class Warehouse:
    """Inventario discreto y determinista sobre 500 estanterias independientes."""

    def __init__(self, horizon: int, seed: int) -> None:
        self.horizon = horizon
        self.seed = seed
        self.rng = random.Random(seed)
        self.shelves: dict[int, tuple[str, int] | None] = {i: None for i in range(SHELF_COUNT)}
        self.step_index = 0
        self.script: list[Observation] = self._build_script()

    def _build_script(self) -> list[Observation]:
        rng = random.Random(self.seed)
        script: list[Observation] = []
        stored: list[str] = []
        for step in range(self.horizon):
            force_store = step == 0 or not stored
            kind = "store" if force_store else rng.choice(["store", "ship", "telemetry"])
            if kind == "store":
                sku = rng.choice(SKUS)
                qty = rng.randint(1, 20)
                stored.append(sku)
                text = f"incoming pallet of {qty} units of {sku}"
                script.append(Observation(step=step, text=text, actionable=True))
            elif kind == "ship":
                # `stored` es el multiconjunto de stock que deja la trayectoria de
                # ground truth: se retira el SKU al emitir su orden, para que ninguna
                # orden pida mercancia que ya salio del almacen.
                sku = rng.choice(stored)
                stored.remove(sku)
                text = f"order received for {sku}"
                script.append(Observation(step=step, text=text, actionable=True))
            else:
                text = rng.choice(
                    [
                        "conveyor belt 3 reports nominal throughput",
                        "night shift roster updated",
                        "humidity sensor calibration completed",
                    ]
                )
                script.append(Observation(step=step, text=text, actionable=False))
        return script

    def reset(self) -> Observation:
        self.shelves = {i: None for i in range(SHELF_COUNT)}
        self.step_index = 0
        return self.script[0]

    def observe(self) -> Observation:
        return self.script[self.step_index]

    @property
    def done(self) -> bool:
        return self.step_index >= self.horizon

    def _first_empty_shelf(self) -> int:
        for index in range(SHELF_COUNT):
            if self.shelves[index] is None:
                return index
        raise RuntimeError("almacen lleno")

    def _shelf_holding(self, sku: str) -> int | None:
        for index, content in self.shelves.items():
            if content is not None and content[0] == sku:
                return index
        return None

    def expected_action(self) -> Action:
        obs = self.observe()
        if not obs.actionable:
            return Action(name="Wait")
        words = obs.text.split()
        if obs.text.startswith("incoming pallet"):
            qty, sku = int(words[3]), words[-1]
            return Action(
                name="Store",
                args={"shelf": self._first_empty_shelf(), "sku": sku, "qty": qty},
            )
        sku = words[-1]
        shelf = self._shelf_holding(sku)
        if shelf is None:
            return Action(name="Wait")
        return Action(name="Ship", args={"shelf": shelf, "sku": sku})

    def apply(self, action: Action) -> None:
        if action.name == "Store":
            shelf = action.args.get("shelf")
            sku = action.args.get("sku")
            qty = action.args.get("qty")
            if isinstance(shelf, int) and 0 <= shelf < SHELF_COUNT:
                self.shelves[shelf] = (str(sku), int(qty or 0))
        elif action.name == "Ship":
            shelf = action.args.get("shelf")
            if isinstance(shelf, int) and 0 <= shelf < SHELF_COUNT:
                self.shelves[shelf] = None
        elif action.name == "Move":
            source, target = action.args.get("from"), action.args.get("to")
            if isinstance(source, int) and isinstance(target, int):
                self.shelves[target] = self.shelves.get(source)
                self.shelves[source] = None
        self.step_index += 1

    def spec(self) -> str:
        return (
            "You operate a warehouse with 500 shelves numbered 0-499.\n"
            "At each step you receive one event and must reply with exactly one action.\n"
            "Actions:\n"
            '  Store({"shelf": <int>, "sku": "<str>", "qty": <int>}) '
            "- put an incoming pallet on the lowest-numbered empty shelf.\n"
            '  Ship({"shelf": <int>, "sku": "<str>"}) '
            "- fulfil an order from the shelf where that SKU is currently stored.\n"
            '  Move({"from": <int>, "to": <int>}) - relocate stock.\n'
            '  Wait({}) - the event needs no action.\n'
            "If the ordered SKU is not currently in stock, reply Wait({}).\n"
        )

    def schema_fields(self) -> list[str]:
        return ["shelf_contents", "last_event"]
