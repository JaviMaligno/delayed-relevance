from __future__ import annotations

import random

from dr.types import Action, Observation

SKUS = [f"SKU-{chr(ord('A') + i)}" for i in range(12)]
SHELF_COUNT = 500

CARRIERS = ["NORTHWIND FREIGHT", "MERIDIAN LOGISTICS", "CALDERA TRANSPORT", "OAKLINE HAULAGE"]
CUSTOMERS = ["ACME INDUSTRIAL", "BRIGHTFOLD RETAIL", "KESTREL SUPPLY", "VANTAGE WHOLESALE"]
SERVICE_LEVELS = ["standard", "next_day", "economy", "expedited"]
SUPPLIER_SITES = ["Rotterdam-04", "Valencia-11", "Gdansk-02", "Leeds-07", "Lyon-09"]
INSPECTIONS = ["passed", "passed_with_note", "spot_check_passed", "not_required"]
REGIONS = ["iberia", "benelux", "nordics", "dach", "britain"]
NOTES = [
    "none",
    "handle_with_standard_care",
    "recurring_supplier_no_issues",
    "operator_confirmed_counts",
    "no_deviation_from_plan",
]
TELEMETRY_SOURCES = [
    ("conveyor_belt_3", "throughput_units_per_min", "nominal"),
    ("humidity_sensor_north", "relative_humidity_pct", "within_band"),
    ("dock_scanner_2", "scan_latency_ms", "nominal"),
    ("hvac_zone_b", "setpoint_deviation_c", "within_band"),
    ("floor_scrubber_1", "battery_pct", "charging"),
]


def _audit_block(rng: random.Random) -> str:
    """Cola de auditoria que llevan todos los eventos.

    No aporta informacion portante a proposito. Existe para igualar la DENSIDAD DE
    CONTEXTO del entorno del paper, no su contenido literal: SkillExecBench no tiene
    codigo publico, asi que lo unico replicable es cuanto contexto ve el modelo por
    paso. Sin esto, el brazo de historia completa nunca alcanza la presion de
    contexto donde el metodo del paper tiene algo que ganar.
    """
    return (
        f"\n  audit_trail_id=AUD-{rng.randint(100000, 999999)} "
        f"| recorded_at=2026-09-{rng.randint(10, 28)}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00Z "
        f"| source_system={rng.choice(['WMS-CORE', 'WMS-EDGE', 'SCADA-2', 'ERP-LINK'])} "
        f"| schema_version={rng.randint(3, 9)}.{rng.randint(0, 9)} "
        f"| ingest_latency_ms={rng.randint(5, 900)} "
        f"| retries={rng.randint(0, 3)} | checksum_ok=true\n"
        f"  reviewed_by=auditor_{rng.randint(100, 999)} "
        f"| review_status={rng.choice(['auto_approved', 'sampled_ok', 'not_sampled'])} "
        f"| retention_years={rng.randint(3, 10)} "
        f"| compliance_tag={rng.choice(['iso9001', 'iso14001', 'gdpr_na', 'none'])} "
        f"| pii_present=false | export_controlled=false "
        f"| archive_batch=ARC-{rng.randint(1000, 9999)}\n"
        f"  upstream_message_id=MSG-{rng.randint(1000000, 9999999)} "
        f"| queue={rng.choice(['inbound.q', 'outbound.q', 'telemetry.q'])} "
        f"| partition={rng.randint(0, 15)} | offset={rng.randint(10000, 999999)} "
        f"| producer={rng.choice(['gateway-a', 'gateway-b', 'gateway-c'])} "
        f"| trace_sampled={rng.choice(['true', 'false'])}\n"
        f"  sla_clock_started=true "
        f"| downstream_ack={rng.choice(['pending', 'received'])} "
        f"| replay_count={rng.randint(0, 2)} "
        f"| environment=production | region_code={rng.choice(REGIONS)} "
        f"| correlation_group=CG-{rng.randint(10000, 99999)} | end_of_record=true"
    )


def event_field(text: str, name: str) -> str | None:
    """Lee un campo `clave=valor` de un registro de evento."""
    for chunk in text.split(" | "):
        key, _, value = chunk.partition("=")
        if key.strip() == name:
            return value.strip()
    return None


class Warehouse:
    """Inventario discreto y determinista sobre 500 estanterias independientes.

    Los eventos son registros estructurados con campos irrelevantes ademas de los
    portantes. Esa densidad es deliberada: con observaciones de una linea corta, el
    brazo de historia completa nunca llega a la presion de contexto donde el metodo
    del paper tiene algo que ganar, y la calibracion mide otra cosa.
    """

    def __init__(self, horizon: int, seed: int) -> None:
        self.horizon = horizon
        self.seed = seed
        self.shelves: dict[int, tuple[str, int, str] | None] = {i: None for i in range(SHELF_COUNT)}
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
                units = rng.randint(1, 20)
                stored.append(sku)
                text = (
                    f"EVENT inbound_pallet | pallet_id=PAL-{rng.randint(1000, 9999)} "
                    f"| sku={sku} | units={units} | lot=L-{rng.randint(1000, 9999)} "
                    f"| carrier={rng.choice(CARRIERS)} | dock={rng.randint(1, 8)} "
                    f"| temperature_c={rng.uniform(1.0, 8.0):.1f} | manifest_ok=true "
                    f"| seal_intact=true | priority={rng.choice(SERVICE_LEVELS)}\n"
                    f"  asn_reference=ASN-{rng.randint(100000, 999999)} "
                    f"| purchase_order=PO-{rng.randint(10000, 99999)} "
                    f"| supplier_site={rng.choice(SUPPLIER_SITES)} "
                    f"| gross_weight_kg={rng.uniform(80.0, 900.0):.1f} "
                    f"| net_weight_kg={rng.uniform(60.0, 850.0):.1f} "
                    f"| pallet_type={rng.choice(['euro', 'industrial', 'half', 'display'])} "
                    f"| height_cm={rng.randint(80, 220)} | stackable={rng.choice(['true', 'false'])}\n"
                    f"  hazmat_class=none | customs_status=cleared "
                    f"| inspection={rng.choice(INSPECTIONS)} "
                    f"| received_by=operator_{rng.randint(100, 999)} "
                    f"| gate_pass=GP-{rng.randint(1000, 9999)} "
                    f"| trailer={rng.choice(['TR-A1', 'TR-B4', 'TR-C7', 'TR-D2'])} "
                    f"| unload_minutes={rng.randint(4, 40)} "
                    f"| damage_report=none | photos_attached={rng.randint(0, 6)}\n"
                    f"  cross_dock_candidate={rng.choice(['true', 'false'])} "
                    f"| putaway_window_minutes={rng.randint(15, 240)} "
                    f"| replenishment_trigger={rng.choice(['none', 'min_max', 'forecast'])} "
                    f"| cycle_count_due={rng.choice(['true', 'false'])} "
                    f"| notes={rng.choice(NOTES)}" + _audit_block(rng)
                )
                script.append(Observation(step=step, text=text, actionable=True))
            elif kind == "ship":
                # `stored` es el multiconjunto de stock que deja la trayectoria de
                # ground truth: se retira el SKU al emitir su orden, para que ninguna
                # orden pida mercancia que ya salio del almacen.
                sku = rng.choice(stored)
                stored.remove(sku)
                text = (
                    f"EVENT outbound_order | order_id=ORD-{rng.randint(1000, 9999)} "
                    f"| sku={sku} | units_requested={rng.randint(1, 20)} "
                    f"| customer={rng.choice(CUSTOMERS)} "
                    f"| service_level={rng.choice(SERVICE_LEVELS)} "
                    f"| carrier_slot=booked | packing_station={rng.randint(1, 6)} "
                    f"| label_printed=true\n"
                    f"  sales_order=SO-{rng.randint(100000, 999999)} "
                    f"| account_manager=rep_{rng.randint(100, 999)} "
                    f"| destination_region={rng.choice(REGIONS)} "
                    f"| incoterm={rng.choice(['DAP', 'EXW', 'CIF', 'FCA'])} "
                    f"| payment_status=cleared | credit_hold=false "
                    f"| requested_ship_date=2026-09-{rng.randint(10, 28)}\n"
                    f"  packaging={rng.choice(['carton', 'shrinkwrap', 'crate', 'tote'])} "
                    f"| fragile={rng.choice(['true', 'false'])} "
                    f"| insurance_value_eur={rng.uniform(200.0, 9000.0):.2f} "
                    f"| route={rng.choice(['R-11', 'R-24', 'R-37', 'R-52'])} "
                    f"| dock_assignment={rng.randint(1, 8)} "
                    f"| pick_wave=W-{rng.randint(100, 999)} "
                    f"| pick_sequence={rng.randint(1, 40)} | consolidation=false\n"
                    f"  backorder_allowed={rng.choice(['true', 'false'])} "
                    f"| partial_shipment={rng.choice(['true', 'false'])} "
                    f"| customer_reference=CR-{rng.randint(10000, 99999)} "
                    f"| sla_hours={rng.randint(12, 96)} "
                    f"| notes={rng.choice(NOTES)}" + _audit_block(rng)
                )
                script.append(Observation(step=step, text=text, actionable=True))
            else:
                source, metric, status = rng.choice(TELEMETRY_SOURCES)
                text = (
                    f"EVENT telemetry | source={source} | metric={metric} "
                    f"| value={rng.uniform(10.0, 200.0):.1f} | status={status} "
                    f"| window=15m | operator=shift_{rng.choice('abc')} "
                    f"| ticket=none | requires_action=false\n"
                    f"  sensor_id=SEN-{rng.randint(1000, 9999)} "
                    f"| firmware={rng.randint(2, 9)}.{rng.randint(0, 9)}.{rng.randint(0, 9)} "
                    f"| last_calibration=2026-0{rng.randint(1, 8)}-{rng.randint(10, 28)} "
                    f"| drift_pct={rng.uniform(0.0, 2.0):.2f} "
                    f"| baseline={rng.uniform(10.0, 200.0):.1f} "
                    f"| upper_limit={rng.uniform(200.0, 400.0):.1f} "
                    f"| lower_limit={rng.uniform(0.0, 10.0):.1f} | alarm_armed=true\n"
                    f"  zone={rng.choice(['north', 'south', 'east', 'west'])} "
                    f"| aisle={rng.randint(1, 24)} | poll_interval_s={rng.randint(5, 120)} "
                    f"| uptime_hours={rng.randint(100, 9000)} "
                    f"| packets_dropped={rng.randint(0, 12)} "
                    f"| maintenance_window=2026-09-{rng.randint(10, 28)} "
                    f"| vendor={rng.choice(['Siemens', 'Honeywell', 'Zebra', 'Datalogic'])}\n"
                    f"  correlation_id=COR-{rng.randint(100000, 999999)} "
                    f"| escalation_policy=none | acknowledged=true "
                    f"| history_window_readings={rng.randint(20, 400)} "
                    f"| notes={rng.choice(NOTES)}" + _audit_block(rng)
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
        """Estanteria de numero mas bajo que contiene el SKU. La regla esta en spec()."""
        for index in range(SHELF_COUNT):
            content = self.shelves.get(index)
            if content is not None and content[0] == sku:
                return index
        return None

    def expected_action(self) -> Action:
        obs = self.observe()
        if not obs.actionable:
            return Action(name="Wait")
        sku = event_field(obs.text, "sku") or ""
        if "inbound_pallet" in obs.text:
            units = int(event_field(obs.text, "units") or 0)
            lot = event_field(obs.text, "lot") or ""
            return Action(
                name="Store",
                args={"shelf": self._first_empty_shelf(), "sku": sku, "units": units, "lot": lot},
            )
        shelf = self._shelf_holding(sku)
        if shelf is None:
            return Action(name="Wait")
        return Action(name="Ship", args={"shelf": shelf, "sku": sku})

    def apply(self, action: Action) -> None:
        if action.name == "Store":
            shelf = action.args.get("shelf")
            if isinstance(shelf, int) and 0 <= shelf < SHELF_COUNT:
                self.shelves[shelf] = (
                    str(action.args.get("sku")),
                    int(action.args.get("units") or 0),
                    str(action.args.get("lot")),
                )
        elif action.name == "Ship":
            shelf = action.args.get("shelf")
            if isinstance(shelf, int) and 0 <= shelf < SHELF_COUNT:
                self.shelves[shelf] = None
        elif action.name == "Move":
            source, target = action.args.get("from"), action.args.get("to")
            in_range = (
                isinstance(source, int)
                and isinstance(target, int)
                and 0 <= source < SHELF_COUNT
                and 0 <= target < SHELF_COUNT
            )
            # Sin validacion, un indice fuera de rango creaba estanterias fantasma y un
            # destino ocupado borraba stock en silencio.
            if in_range and self.shelves[source] is not None and self.shelves[target] is None:
                self.shelves[target] = self.shelves[source]
                self.shelves[source] = None
        self.step_index += 1

    def spec(self) -> str:
        return (
            "WAREHOUSE OPERATING PROCEDURE\n"
            "\n"
            "You are the execution controller for a distribution warehouse with 500 storage\n"
            "shelves, numbered 0 to 499. Shelves are single-occupancy: a shelf holds either\n"
            "exactly one pallet or nothing at all. You receive one event per step and must\n"
            "reply with exactly one action. There is no queue and no batching: the event in\n"
            "front of you is resolved before the next one arrives.\n"
            "\n"
            "EVENT FORMAT\n"
            "Every event is a pipe-separated record of key=value fields, beginning with the\n"
            "event type. Most fields are operational metadata that do not affect your action\n"
            "(carrier, dock, temperature_c, customer, service_level, packing_station,\n"
            "operator, ticket, and so on). Read the type first, then only the fields the\n"
            "procedure below tells you to use.\n"
            "\n"
            "EVENT TYPES\n"
            "  inbound_pallet - a pallet has arrived at a dock and must be put away.\n"
            "      Load-bearing fields: sku, units, lot.\n"
            "  outbound_order - a customer order must be fulfilled from stock on hand.\n"
            "      Load-bearing field: sku.\n"
            "  telemetry      - a status reading from equipment or facilities.\n"
            "      No load-bearing fields. Telemetry never requires an action.\n"
            "\n"
            "ACTIONS\n"
            '  Store({"shelf": <int>, "sku": "<str>", "units": <int>, "lot": "<str>"})\n'
            "      Put an inbound pallet away. The shelf MUST be the lowest-numbered shelf\n"
            "      that is currently empty. Copy sku, units and lot from the event verbatim.\n"
            '  Ship({"shelf": <int>, "sku": "<str>"})\n'
            "      Fulfil an outbound order. The shelf MUST be the one where that SKU is\n"
            "      currently stored. If several shelves hold the same SKU, ship from the\n"
            "      lowest-numbered one. Shipping empties the shelf.\n"
            '  Move({"from": <int>, "to": <int>})\n'
            "      Relocate a pallet between shelves. The source must hold stock and the\n"
            "      destination must be empty. Not required by the routine procedure.\n"
            "  Wait({})\n"
            "      The event requires no action.\n"
            "\n"
            "PROCEDURE\n"
            "  1. On inbound_pallet: find the lowest-numbered empty shelf and Store there.\n"
            "     Because shelves are freed by shipping, the lowest empty shelf is often NOT\n"
            "     the next one after your last put-away - a shelf emptied earlier is reused\n"
            "     before any higher-numbered shelf that has never been filled.\n"
            "  2. On outbound_order: recall which shelf holds that SKU and Ship from it.\n"
            "     If the ordered SKU is not currently in stock, reply Wait({}).\n"
            "  3. On telemetry: reply Wait({}).\n"
            "\n"
            "WHAT MAKES THIS HARD\n"
            "Shelf occupancy is not derivable from the current event. It is the accumulated\n"
            "consequence of every Store and Ship you have performed so far. A single missed\n"
            "or misremembered put-away silently invalidates every later put-away and every\n"
            "later shipment of that SKU, because the lowest-empty-shelf calculation and the\n"
            "SKU lookup both read from that same occupancy map.\n"
            "\n"
            "WORKED EXAMPLES\n"
            "  Example A. The warehouse is empty. An inbound_pallet arrives with sku=SKU-C,\n"
            "  units=8, lot=L-2210. Shelves 0 and above are all empty, so the lowest empty\n"
            "  shelf is 0. The correct action is:\n"
            '      Store({"shelf": 0, "sku": "SKU-C", "units": 8, "lot": "L-2210"})\n'
            "\n"
            "  Example B. Shelves 0, 1 and 2 hold stock; shelf 1 holds SKU-C. An\n"
            "  outbound_order arrives for sku=SKU-C. The correct action is:\n"
            '      Ship({"shelf": 1, "sku": "SKU-C"})\n'
            "  Shelf 1 is now empty. If an inbound_pallet arrives next, it goes to shelf 1 -\n"
            "  not shelf 3 - because 1 is now the lowest-numbered empty shelf.\n"
            "\n"
            "  Example C. An outbound_order arrives for sku=SKU-K and no shelf holds SKU-K,\n"
            "  either because it never arrived or because it was already shipped. The\n"
            "  correct action is Wait({}). Do not invent a shelf number, and do not ship\n"
            "  from a shelf holding a different SKU.\n"
            "\n"
            "  Example D. A telemetry event reports status=within_band on hvac_zone_b. No\n"
            "  matter what the readings say, the correct action is Wait({}). Telemetry never\n"
            "  changes shelf occupancy and never requires a Store, Ship or Move.\n"
            "\n"
            "CONVENTIONS AND EDGE CASES\n"
            "  - Shelf numbering starts at 0, not 1. The first put-away of an empty\n"
            "    warehouse goes to shelf 0.\n"
            "  - Never Store onto a shelf that already holds a pallet. Single occupancy is\n"
            "    strict, and a Store onto an occupied shelf is treated as a wrong action.\n"
            "  - Never Ship from an empty shelf. Confirm the SKU is in stock first.\n"
            "  - Copy identifiers exactly as they appear in the event. Do not reformat lot\n"
            "    numbers, do not pad shelf numbers, do not translate SKU codes.\n"
            "  - units is an integer count of items on the pallet. units_requested on an\n"
            "    outbound_order is NOT necessarily equal to the units stored, and does not\n"
            "    change which shelf you ship from. Partial shipment is out of scope.\n"
            "  - Fields such as priority, service_level, dock and packing_station never\n"
            "    change which action is correct, and never change which shelf is chosen.\n"
            "  - The audit tail at the end of every record is bookkeeping. It never carries\n"
            "    an instruction and never changes the action.\n"
            "\n"
            "OUTPUT\n"
            "Emit exactly one action per step, in the exact form shown above, with a JSON\n"
            "object as the single argument. Do not emit two actions. Do not omit the JSON.\n"
        )

    def schema_fields(self) -> list[str]:
        return ["shelf_contents", "last_event"]
