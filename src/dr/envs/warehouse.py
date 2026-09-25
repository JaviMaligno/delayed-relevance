from __future__ import annotations

import random

from dr.envs.longspec import apendice
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


MAINTENANCE_REASONS = ("rail_wear", "sensor_fault", "beam_deflection",
                       "fire_sprinkler_check", "anchor_bolt_torque")


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

    def __init__(
        self,
        horizon: int,
        seed: int,
        latent_k: int | None = None,
        latent_control: bool = False,
        oracle_schema: bool = False,
        hatch_schema: bool = False,
        reminder: bool = False,
        reminder_raw: bool = False,
        long_spec: bool = False,
        invalidation_k: int | None = None,
        apendice_b: bool = False,
        sin_telemetria: bool = False,
        ruido: int = 0,
        latent_estricto: bool = False,
    ) -> None:
        """`latent_k` activa la sonda de relevancia diferida.

        En el paso `t` el entorno anuncia que una estanteria queda en cuarentena. El
        aviso es indistinguible del ruido de fondo y no afecta a la accion en curso.
        En `t + latent_k` esa estanteria es la libre mas baja, asi que la accion
        correcta es saltarsela. Quien perdio el aviso almacena ahi y falla.

        `latent_control=True` pone en cuarentena una estanteria que nunca llega a ser
        la libre mas baja: el aviso llega igual pero nunca es portante. Todos los
        runtimes deben puntuar igual que sin sonda; si no, el efecto medido no es la
        relevancia diferida sino la presencia del aviso.
        """
        self.horizon = horizon
        self.seed = seed
        self.latent_k = latent_k
        # Revision adversarial 6: el generador no comprobaba que el hecho no importara
        # antes de t+k, y en la mayoria de las seeds importaba a los 5-8 pasos. En modo
        # estricto solo se acepta un escenario si, con la politica correcta y el aviso
        # ya colocado, el hecho cambia la accion por PRIMERA vez justo en t+k. Por
        # defecto desactivado: lo ya medido no se mueve.
        self.latent_estricto = latent_estricto
        self.latent_control = latent_control
        self.oracle_schema = oracle_schema
        self.hatch_schema = hatch_schema
        self.reminder = reminder
        # `reminder_raw` repite el aviso ENTERO, tal como llego, en vez de los tres
        # campos portantes. Separa dos explicaciones del efecto del recordatorio que
        # hasta ahora iban juntas: si basta con que el hecho este disponible, o si hace
        # falta ademas que este destilado. El aviso original ya dice `do_not_store=true`,
        # asi que la diferencia entre las dos condiciones no es la instruccion: es que
        # una trae 3 campos y la otra los mismos 3 enterrados entre otros quince.
        self.reminder_raw = reminder_raw
        # `long_spec` anade la referencia de campos, las excepciones y los ejemplos
        # resueltos, que llevan el procedimiento por encima del prefijo minimo
        # cacheable (4.096 tokens, medidos). Sin eso la tabla de coste solo mide el
        # caso en que NADA cachea salvo la historia acumulada de ReAct.
        self.long_spec = long_spec
        self.quarantine_notice_text: str | None = None
        # `apendice_b` cierra los dos huecos que I4 encontro contra su Apendice B:
        # los eventos de mantenimiento que obligan a `Move`, y el rechazo de acciones
        # invalidas con observacion de error local. Va detras de bandera porque
        # cambiarlo por debajo invalidaria los 100 episodios de R1 de golpe; con
        # bandera, la diferencia entre las dos variantes ES la medida del hueco.
        self.apendice_b = apendice_b
        # Hueco 3 de I4. Su Algoritmo 2 no tiene familia no accionable: `Receive`
        # siempre, y `Order`/`Maintenance` en cuanto hay stock. Nuestra telemetria es
        # un paso propio, asi que un tercio de nuestra historia no muta el estado: el
        # transcript crece igual pero hay menos que recordar.
        self.sin_telemetria = sin_telemetria
        # Su ruido del Apendice C es otra cosa y va en su sitio: anexado a la
        # observacion de un evento real, bajo su cabecera, y sin tocar el estado.
        self.ruido = ruido
        self.rechazo: tuple[int, str] | None = None
        self.invalidation_k = invalidation_k
        self.invalidation_from: int | None = None
        self.invalidated_shelf: int | None = None
        self.shelves: dict[int, tuple[str, int, str] | None] = {i: None for i in range(SHELF_COUNT)}
        self.step_index = 0
        self.quarantined_shelf: int | None = None
        self.quarantine_from: int | None = None
        self.dependent_step: int | None = None
        self.script: list[Observation] = self._build_script()
        if latent_k is not None:
            self._plant_latent_rule(latent_k)
        if invalidation_k is not None:
            self._plant_invalidation(invalidation_k)

    def _canonical_first_empty(self) -> list[tuple[int, int]]:
        """Simula la trayectoria del oraculo y devuelve (paso, estanteria libre mas baja)
        para cada evento de entrada. Sirve para elegir donde plantar la regla latente."""
        ocupadas: dict[int, str] = {}
        puntos: list[tuple[int, int]] = []

        def primera_libre() -> int:
            i = 0
            while i in ocupadas:
                i += 1
            return i

        for paso, obs in enumerate(self.script):
            if "inbound_pallet" in obs.text:
                libre = primera_libre()
                puntos.append((paso, libre))
                ocupadas[libre] = event_field(obs.text, "sku") or ""
            elif "outbound_order" in obs.text:
                sku = event_field(obs.text, "sku") or ""
                for i in sorted(ocupadas):
                    if ocupadas[i] == sku:
                        del ocupadas[i]
                        break
        return puntos

    def _plant_latent_rule(self, k: int) -> None:
        candidatos = [(p, s) for p, s in self._canonical_first_empty() if p - k >= 0]
        if not candidatos:
            raise ValueError(f"horizonte {self.horizon} demasiado corto para k={k}")
        # El mas tardio deja el maximo de historia antes del aviso.
        if self.latent_estricto:
            elegido = next((c for c in reversed(candidatos) if self._escenario_limpio(c, k)), None)
            if elegido is None:
                raise ValueError(f"seed {self.seed}: ningun escenario donde el hecho importe "
                                 f"por primera vez justo en t+{k}")
            paso_dependiente, estanteria = elegido
        else:
            paso_dependiente, estanteria = candidatos[-1]
        self._plantar_aviso(paso_dependiente, estanteria, k)

    def _escenario_limpio(self, candidato: tuple[int, int], k: int) -> bool:
        """Con el aviso ya colocado (sustituye al evento de su paso), la politica
        correcta ve cambiar su accion por la cuarentena por primera vez en t+k."""
        import copy
        prueba = copy.deepcopy(self)
        prueba._plantar_aviso(candidato[0], candidato[1], k)
        prueba.reset()
        while not prueba.done:
            prueba.observe()
            sin = copy.deepcopy(prueba)
            sin.quarantined_shelf = None
            if prueba.expected_action().render() != sin.expected_action().render():
                return prueba.step_index == candidato[0]
            prueba.apply(prueba.expected_action())
        return False

    def _plantar_aviso(self, paso_dependiente: int, estanteria: int, k: int) -> None:
        paso_aviso = paso_dependiente - k
        self.dependent_step = paso_dependiente
        self.quarantine_from = paso_aviso
        # En la condicion de control la cuarentena cae sobre una estanteria que nunca
        # llega a ser la libre mas baja, asi que el aviso nunca es portante.
        self.quarantined_shelf = SHELF_COUNT - 1 if self.latent_control else estanteria
        rng = random.Random(self.seed * 7919 + k)
        self.script[paso_aviso] = Observation(
            step=paso_aviso,
            text=(
                f"EVENT facility_notice | notice_id=FAC-{rng.randint(1000, 9999)} "
                f"| shelf={self.quarantined_shelf} | status=quarantined "
                f"| reason=scheduled_maintenance | effective=immediately "
                f"| do_not_store=true | expires=none\n"
                f"  raised_by=facilities_{rng.randint(100, 999)} "
                f"| work_order=WO-{rng.randint(10000, 99999)} "
                f"| contractor={rng.choice(CARRIERS)} "
                f"| estimated_duration_days={rng.randint(3, 30)} "
                f"| access_restricted=true | signage_posted=true"
                + _audit_block(rng)
            ),
            actionable=False,
        )
        self.quarantine_notice_text = self.script[paso_aviso].text

    def _plant_invalidation(self, k: int) -> None:
        """Sonda C: invalidacion retroactiva, con metrica de PROMEDIO y no de evento.

        En el paso `t` el agente almacena en la estanteria S. En `t+k` llega un aviso
        de que aquella colocacion nunca se completo y S esta en realidad vacia. Desde
        ese momento S es la libre mas baja, asi que **todos** los `Store` posteriores
        dependen de haber aplicado la correccion, no solo el siguiente.

        Esa eleccion es deliberada: la misma pregunta formulada como "acerto el paso
        siguiente" tiene ~50 puntos de ruido de muestreo; formulada como score sobre
        el tramo posterior promedia quince o veinte eventos y el ruido casi desaparece.
        Ademas mide mejor lo que interesa: no si se recupero una vez, sino si SIGUIO
        recuperado.
        """
        puntos = self._canonical_first_empty()
        candidatos = [(p, s) for p, s in puntos if p + k < self.horizon - 4]
        if not candidatos:
            raise ValueError(f"horizonte {self.horizon} demasiado corto para invalidacion k={k}")
        paso_store, estanteria = candidatos[0]
        self.invalidated_shelf = estanteria
        self.invalidation_from = paso_store + k
        rng = random.Random(self.seed * 6271 + k)
        self.script[self.invalidation_from] = Observation(
            step=self.invalidation_from,
            text=(
                f"EVENT correction_notice | notice_id=COR-{rng.randint(1000, 9999)} "
                f"| corrects_step={paso_store} | shelf={estanteria} "
                f"| finding=putaway_never_completed | shelf_is_now=empty "
                f"| stock_removed=true | confidence=confirmed\n"
                f"  raised_by=cycle_count_team_{rng.randint(10, 99)} "
                f"| audit_ref=AUD-{rng.randint(10000, 99999)} "
                f"| recount_performed=true | discrepancy_closed=true "
                f"| supersedes_prior_record=true"
                + _audit_block(rng)
            ),
            actionable=False,
        )

    def _apply_invalidation_if_due(self) -> None:
        """Al llegar el aviso, el estado VERDADERO cambia: la estanteria queda vacia."""
        if (
            self.invalidation_from is not None
            and self.invalidated_shelf is not None
            and self.step_index == self.invalidation_from
        ):
            self.shelves[self.invalidated_shelf] = None

    def _is_quarantined(self, shelf: int) -> bool:
        return (
            self.quarantined_shelf == shelf
            and self.quarantine_from is not None
            and self.step_index >= self.quarantine_from
        )

    def _build_script(self) -> list[Observation]:
        rng = random.Random(self.seed)
        script: list[Observation] = []
        stored: list[str] = []
        # Estado canonico de estanterias, solo con `apendice_b`: un evento de
        # mantenimiento tiene que nombrar una estanteria que de verdad este ocupada en
        # la trayectoria de ground truth, y el guion se construye antes de correr.
        canonico: dict[int, str] = {}

        def libre_canonica(excepto: int | None = None) -> int:
            indice = 0
            while indice in canonico or indice == excepto:
                indice += 1
            return indice

        for step in range(self.horizon):
            force_store = step == 0 or not stored
            opciones = ["store"] if self.sin_telemetria else ["store", "ship", "telemetry"]
            if self.sin_telemetria and stored:
                opciones.append("ship")
            if self.apendice_b and canonico:
                opciones.append("maintenance")
            kind = "store" if force_store else rng.choice(opciones)
            if kind == "store":
                sku = rng.choice(SKUS)
                units = rng.randint(1, 20)
                stored.append(sku)
                if self.apendice_b:
                    canonico[libre_canonica()] = sku
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
                if self.apendice_b:
                    for indice in sorted(canonico):
                        if canonico[indice] == sku:
                            del canonico[indice]
                            break
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
            elif kind == "maintenance":
                # Su Algoritmo 2 sortea `Maintenance required on [shelf]`, que obliga a
                # reubicar. Es la unica accion que cruza dos partes del estado en un
                # solo paso: donde esta la pieza y que hueco esta libre.
                estante = rng.choice(sorted(canonico))
                destino = libre_canonica(excepto=estante)
                canonico[destino] = canonico.pop(estante)
                text = (
                    f"EVENT maintenance_required | work_order=WO-{rng.randint(1000, 9999)} "
                    f"| shelf={estante} | reason={rng.choice(MAINTENANCE_REASONS)} "
                    f"| crew={rng.choice(['alpha', 'bravo', 'charlie'])} "
                    f"| window_minutes={rng.randint(30, 240)} | shelf_must_be_cleared=true\n"
                    f"  permit=PRM-{rng.randint(10000, 99999)} "
                    f"| contractor={rng.choice(['Vanderlande', 'Dematic', 'Knapp', 'SSI'])} "
                    f"| risk_assessment=filed | lockout_tagout=true "
                    f"| scaffolding={rng.choice(['true', 'false'])} "
                    f"| aisle={rng.randint(1, 24)} | zone={rng.choice(['north', 'south'])}\n"
                    f"  reported_by=operator_{rng.randint(100, 999)} "
                    f"| severity={rng.choice(['low', 'medium', 'high'])} "
                    f"| downtime_estimate_h={rng.randint(1, 12)} "
                    f"| parts_ordered={rng.choice(['true', 'false'])} "
                    f"| vendor_ticket=VT-{rng.randint(1000, 9999)} "
                    f"| recurring={rng.choice(['true', 'false'])}\n"
                    f"  last_service=2026-0{rng.randint(1, 8)}-{rng.randint(10, 28)} "
                    f"| inspection_due=2026-09-{rng.randint(10, 28)} "
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
        if self.ruido:
            script = [Observation(step=o.step,
                                  text=o.text + "\n" + self._bloque_de_ruido(rng),
                                  actionable=o.actionable)
                      for o in script]
        return script

    def _bloque_de_ruido(self, rng: random.Random) -> str:
        """Su Apendice C: distractores anexados bajo cabecera, aleatorios en cada paso
        y sin efecto sobre el estado. Se generan con el mismo `rng` del guion para que
        la reproducibilidad por seed siga valiendo."""
        lineas = []
        for _ in range(self.ruido):
            clase = rng.choice(("robot", "sensor", "syslog"))
            if clase == "robot":
                lineas.append(
                    f"[Robot-{rng.randint(1, 40)}] Battery: {rng.randint(10, 100)}%, "
                    f"Temperature: {rng.randint(20, 60)}C, CPU Load: {rng.randint(5, 99)}%, "
                    f"Speed: {rng.uniform(0.2, 2.0):.1f} m/s, "
                    f"Nav Confidence: {rng.uniform(80.0, 99.9):.1f}%")
            elif clase == "sensor":
                lineas.append(
                    f"[Sensor] Humidity: {rng.uniform(20.0, 70.0):.1f}%, "
                    f"Ambient: {rng.uniform(12.0, 28.0):.1f}C, "
                    f"Air Quality: {rng.randint(10, 90)}, "
                    f"Zone: {rng.choice(('north', 'south', 'east', 'west'))}")
            else:
                lineas.append(
                    f"[Syslog] Server-{rng.randint(10, 99)} CPU load: {rng.randint(5, 99)}%, "
                    f"RAM usage: {rng.randint(20, 95)}%")
        return "--- BACKGROUND TELEMETRY ---\n" + "\n".join(lineas)

    def reset(self) -> Observation:
        self.shelves = {i: None for i in range(SHELF_COUNT)}
        self.step_index = 0
        self._apply_invalidation_if_due()
        return self.script[0]

    def observe(self) -> Observation:
        obs = self.script[self.step_index]
        if self.rechazo is not None and self.rechazo[0] == self.step_index:
            # No se consume aqui: `expected_action` tambien llama a `observe`, y una
            # observacion que cambia segun quien la mire no es una observacion.
            obs = Observation(step=obs.step,
                              text=self.rechazo[1] + "\n" + obs.text,
                              actionable=obs.actionable)
        if not (self.reminder or self.reminder_raw) or self.quarantined_shelf is None:
            return obs
        if self.quarantine_from is None or self.step_index <= self.quarantine_from:
            return obs
        if self.reminder_raw:
            # Misma posicion y misma cabecera que el recordatorio destilado; lo unico
            # que cambia es que el contenido viene sin destilar.
            return Observation(
                step=obs.step,
                text=("STANDING NOTICE (as originally filed):\n"
                      f"{self.quarantine_notice_text}\n" + obs.text),
                actionable=obs.actionable,
            )
        # Condicion de recordatorio: el hecho viaja PEGADO a la decision, en cada
        # observacion posterior al aviso. El agente no necesita recordar nada ni
        # tener donde guardarlo. Separa "el campo del esquema sirve de almacen" de
        # "sirve de recordatorio situado donde el modelo mira".
        return Observation(
            step=obs.step,
            text=(f"STANDING NOTICE | shelf={self.quarantined_shelf} | status=quarantined "
                  f"| do_not_store=true\n" + obs.text),
            actionable=obs.actionable,
        )

    @property
    def done(self) -> bool:
        return self.step_index >= self.horizon

    def _first_empty_shelf(self) -> int:
        for index in range(SHELF_COUNT):
            if self.shelves[index] is None and not self._is_quarantined(index):
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
        if "maintenance_required" in obs.text:
            estante = int(event_field(obs.text, "shelf") or -1)
            if not (0 <= estante < SHELF_COUNT) or self.shelves[estante] is None:
                # La estanteria que hay que vaciar ya esta vacia: no hay nada que
                # reubicar. Pasa si el agente se desvio antes; el ground truth no.
                return Action(name="Wait")
            destino = next(i for i in range(SHELF_COUNT)
                           if self.shelves[i] is None and i != estante
                           and not self._is_quarantined(i))
            return Action(name="Move", args={"from": estante, "to": destino})
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

    def _rechazar(self, motivo: str) -> None:
        """Su Apendice B: una accion invalida devuelve una observacion de error local y
        **rechaza la transicion**. El error se cuelga del paso siguiente, que es donde
        el agente lo vera; no gasta un paso ni toca el denominador del score."""
        self.rechazo = (self.step_index + 1, motivo)

    def apply(self, action: Action) -> None:
        if action.name == "Store":
            shelf = action.args.get("shelf")
            if (self.apendice_b and isinstance(shelf, int) and 0 <= shelf < SHELF_COUNT
                    and self.shelves[shelf] is not None):
                self._rechazar(
                    f"ACTION REJECTED: shelf {shelf} is already occupied; "
                    "the state transition was not applied")
                shelf = None
            if isinstance(shelf, int) and 0 <= shelf < SHELF_COUNT:
                self.shelves[shelf] = (
                    str(action.args.get("sku")),
                    int(action.args.get("units") or 0),
                    str(action.args.get("lot")),
                )
        elif action.name == "Ship":
            shelf = action.args.get("shelf")
            if self.apendice_b and isinstance(shelf, int) and 0 <= shelf < SHELF_COUNT:
                contenido = self.shelves[shelf]
                pedido = str(action.args.get("sku"))
                if contenido is None or contenido[0] != pedido:
                    tenia = "nothing" if contenido is None else contenido[0]
                    self._rechazar(
                        f"ACTION REJECTED: shelf {shelf} holds {tenia}, not {pedido}; "
                        "the state transition was not applied")
                    shelf = None
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
            elif self.apendice_b:
                self._rechazar(
                    f"ACTION REJECTED: cannot move from {source} to {target}; the source "
                    "must hold stock and the destination must be empty")
        self.step_index += 1
        self._apply_invalidation_if_due()

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
            + ("" if self.sin_telemetria else
               "  telemetry      - a status reading from equipment or facilities.\n"
               "      No load-bearing fields. Telemetry never requires an action.\n")
            + ("  maintenance_required - a shelf must be cleared for maintenance work.\n"
               "      Load-bearing field: shelf.\n" if self.apendice_b else "")
            + "\n"
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
            + ("" if self.sin_telemetria else "  3. On telemetry: reply Wait({}).\n")
            + ("  4. On maintenance_required: the named shelf must be emptied. Move its\n"
               "     pallet to the lowest-numbered shelf that is currently empty. If the\n"
               "     named shelf is already empty, reply Wait({}).\n"
               "\n"
               "INVALID ACTIONS\n"
               "An action that violates the rules above is rejected: the state does not\n"
               "change, and the next event you see is prefixed with a line beginning\n"
               "ACTION REJECTED explaining why. A rejected action still counts as your\n"
               "answer for that event - there is no retry.\n" if self.apendice_b else "")
            + "\n"
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
            + ("" if self.sin_telemetria else
               "  Example D. A telemetry event reports status=within_band on hvac_zone_b. No\n"
               "  matter what the readings say, the correct action is Wait({}). Telemetry never\n"
               "  changes shelf occupancy and never requires a Store, Ship or Move.\n"
               "\n")
            + "CONVENTIONS AND EDGE CASES\n"
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
            "\n"
            "Keep your reasoning under 60 words, then emit the action. Brevity is a hard\n"
            "requirement: a long answer is cut off before the action is written, and a step\n"
            "without an action counts as a wrong action.\n"
            + (apendice(self) if self.long_spec else "")
        )

    def schema_fields(self) -> list[str]:
        """Campos del esquema de estado.

        `oracle_schema` anade un sitio donde guardar la cuarentena. Es la cota
        superior del spec (§4.4): mide cuanto del fallo se debe a la distancia y
        cuanto a que el hecho no tenia donde vivir. El nombre del campo delata que
        las cuarentenas importan, y eso es deliberado: es lo que la convierte en cota
        superior y no en una condicion mas.
        """
        campos = ["shelf_contents", "last_event"]
        if self.oracle_schema:
            campos.append("quarantined_shelves")
        if self.hatch_schema:
            # Escotilla libre (spec 4.4): da sitio SIN decir para que. Separa "tenia
            # donde guardarlo" de "le avisamos de que importaba", que el campo con
            # nombre delator confunde.
            campos.append("notes")
        return campos
