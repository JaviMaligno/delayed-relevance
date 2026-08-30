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
                sku = rng.choice(stored)
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
