"""Apendice de referencia que lleva la especificacion por encima del minimo cacheable.

La tabla de coste del bloque 1 se midio con una especificacion de ~1.500 tokens, por
debajo del prefijo minimo que Anthropic cachea (medido: 4.096 tokens exactos en Haiku
4.5 — 3.984 no cachea, 4.116 si). Con la especificacion por debajo del umbral, el
bloque de sistema no cachea en NINGUN brazo, y solo ReAct cachea porque su historia
acumulada empuja el prefijo por encima. Eso convierte "los metodos que comprimen
ahorran 0%" en una afirmacion sobre la longitud de nuestro prompt, no sobre el metodo.

Este modulo aporta el caso complementario, que es ademas el mas parecido a un
despliegue real: un procedimiento largo. El contenido no es relleno — es la referencia
de campos que realmente llevan los eventos de este entorno, las reglas de excepcion, y
ejemplos resueltos generados del propio simulador. Un procedimiento operativo de verdad
tiene exactamente esta forma y esta longitud.
"""
from __future__ import annotations

# Los 112 campos que aparecen en los eventos, agrupados por para que sirven. Solo los
# cuatro primeros grupos son portantes; el resto se documenta precisamente porque en un
# procedimiento real hay que decir de cada campo que NO hay que hacer nada con el.
GRUPOS: dict[str, tuple[str, list[str]]] = {
    "Identity of the goods": (
        "These identify what is on the pallet or what is being requested. `sku` is the "
        "only one the procedure reads to decide an action.",
        ["sku", "lot", "units", "units_requested", "pallet_id", "pallet_type"],
    ),
    "Order and document references": (
        "Cross-references into upstream systems. None of them changes which action is "
        "correct; they exist so an auditor can reconstruct the paper trail.",
        ["order_id", "purchase_order", "sales_order", "asn_reference", "customer_reference",
         "manifest_ok", "gate_pass", "audit_trail_id", "correlation_id", "correlation_group",
         "upstream_message_id", "archive_batch"],
    ),
    "Counterparties": (
        "Who the goods come from or go to. Never load-bearing.",
        ["supplier_site", "customer", "carrier", "vendor", "account_manager", "operator",
         "received_by", "reviewed_by", "producer", "destination_region", "region_code",
         "route"],
    ),
    "Physical handling": (
        "Descriptions of the physical unit. The procedure does not consult any of them "
        "when choosing a shelf: shelves are interchangeable and single-occupancy.",
        ["gross_weight_kg", "net_weight_kg", "height_cm", "stackable", "fragile",
         "packaging", "seal_intact", "damage_report", "photos_attached", "inspection",
         "temperature_c", "hazmat_class"],
    ),
    "Dock and staging": (
        "Where the truck is and who unloads it. Operationally important, procedurally "
        "irrelevant.",
        ["dock", "dock_assignment", "trailer", "carrier_slot", "unload_minutes",
         "packing_station", "pick_wave", "pick_sequence", "cross_dock_candidate",
         "consolidation", "replenishment_trigger", "putaway_window_minutes"],
    ),
    "Commercial and compliance": (
        "Contractual and regulatory metadata. It can block a shipment in the real world; "
        "in this procedure it never changes the action.",
        ["service_level", "priority", "incoterm", "payment_status", "credit_hold",
         "insurance_value_eur", "customs_status", "export_controlled", "compliance_tag",
         "pii_present", "retention_years", "review_status", "backorder_allowed",
         "partial_shipment", "requested_ship_date", "sla_hours", "sla_clock_started"],
    ),
    "Record bookkeeping": (
        "Present on every record without exception. Always ignore.",
        ["recorded_at", "schema_version", "checksum_ok", "source", "source_system",
         "environment", "partition", "offset", "queue", "producer", "retries",
         "replay_count", "trace_sampled", "ingest_latency_ms", "downstream_ack",
         "label_printed", "end_of_record", "notes", "ticket", "status"],
    ),
    "Telemetry": (
        "Only ever appears on telemetry events, which are never actionable. A telemetry "
        "record always resolves to Wait, whatever its values say.",
        ["metric", "value", "baseline", "upper_limit", "lower_limit", "drift_pct",
         "sensor_id", "firmware", "last_calibration", "alarm_armed", "acknowledged",
         "escalation_policy", "poll_interval_s", "uptime_hours", "packets_dropped",
         "history_window_readings", "maintenance_window", "window", "zone", "aisle",
         "requires_action", "cycle_count_due"],
    ),
}

EXCEPCIONES = """EXCEPTION HANDLING

  E1. An outbound_order for a sku that is not on any shelf resolves to Wait. Do not
      guess a shelf, and do not ship a different sku with a similar code.
  E2. An inbound_pallet whose sku is already stored elsewhere is still a new pallet
      and still takes the lowest free shelf. Shelves are single-occupancy; never
      merge two pallets onto one shelf.
  E3. A record whose type field you do not recognise resolves to Wait.
  E4. A record that carries a status, alarm or exception field set to a worrying
      value does NOT change the action. Only the record type and the fields named in
      the procedure do.
  E5. If two records appear to conflict, the later one is authoritative. A record
      that explicitly corrects, supersedes or retracts an earlier one replaces it,
      and every later decision must be taken against the corrected picture.
  E6. Never emit more than one action, and never emit an action without its JSON
      argument object. A step that produces no parsable action is scored as wrong.
"""

CIERRE = """WHY THIS REFERENCE EXISTS

Most of the fields above are listed so that you can confirm, without hesitating, that
they are not your concern. The records in this facility are wide by design: they are
written once and read by a dozen downstream systems, each of which needs different
fields. Your slice of that record is small and fixed. Read the type, read the two or
three fields the procedure names for that type, apply the rule, emit the action.
"""


def _referencia_campos() -> str:
    lineas = ["FIELD REFERENCE",
              "",
              "Every field that can appear on a record, and whether the procedure reads it.",
              ""]
    for titulo, (glosa, campos) in GRUPOS.items():
        lineas.append(f"  {titulo}")
        # La glosa se parte a mano en lineas cortas: un procedimiento operativo se lee
        # en una terminal, no en un navegador.
        palabras, actual = glosa.split(), "   "
        for palabra in palabras:
            if len(actual) + len(palabra) + 1 > 78:
                lineas.append(actual)
                actual = "   "
            actual += " " + palabra
        lineas.append(actual)
        for campo in campos:
            lineas.append(f"      {campo}")
        lineas.append("")
    return "\n".join(lineas)


def _ejemplos(entorno) -> str:
    """Ejemplos resueltos tomados del propio simulador, con su accion correcta.

    Se generan de una seed que no se usa en ningun experimento, para que un episodio
    medido nunca contenga el mismo registro que su propio procedimiento cita.
    """
    from dr.envs.warehouse import Warehouse

    muestra = Warehouse(horizon=40, seed=999)
    muestra.reset()
    ejemplos, vistos = [], set()
    while not muestra.done and len(ejemplos) < 5:
        obs = muestra.observe()
        tipo = obs.text.split("|")[0].replace("EVENT", "").strip()
        if tipo not in vistos or len(ejemplos) < 5:
            vistos.add(tipo)
            ejemplos.append((obs.text, muestra.expected_action().render()))
        muestra.apply(muestra.expected_action())
    partes = ["WORKED EXAMPLES",
              "",
              "Five records taken from a completed run, with the action each one required.",
              ""]
    for i, (texto, accion) in enumerate(ejemplos, 1):
        partes.append(f"  Example {i}")
        for linea in texto.split("\n"):
            partes.append(f"    {linea.strip()}")
        partes.append(f"    -> {accion}")
        partes.append("")
    return "\n".join(partes)


def apendice(entorno) -> str:
    return "\n" + "\n".join([_referencia_campos(), EXCEPCIONES, _ejemplos(entorno), CIERRE])
