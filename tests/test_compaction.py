import pytest

from dr.llm import Completion, FakeClient
from dr.runtimes.compaction import (
    BRAZOS,
    FreshLookupRuntime,
    HybridLookupRuntime,
    SummaryLookupRuntime,
    SummaryRuntime,
    palabras_de,
    pedido_de_consulta,
)
from dr.types import Observation

WAIT = "Action: Wait({})"


class GuionCliente(FakeClient):
    """FakeClient que contesta los resumenes aparte: asi el guion de decisiones no
    depende de en que paso cae cada compactacion."""

    def __init__(self, responses):
        super().__init__(responses=list(responses))
        self.resumenes = 0

    def complete(self, system, user, max_tokens=None, cache_prefix=None):
        if system.startswith("Summarise"):
            self.resumenes += 1
            self.calls.append((system, user))
            return Completion(text=f"RESUMEN-{self.resumenes}", prompt_tokens=1, output_tokens=1)
        return super().complete(system, user, max_tokens, cache_prefix)


def _obs(paso, texto=None):
    return Observation(step=paso, text=texto or f"EVENT telemetry | id=E{paso}\n  cola{paso}",
                       actionable=False)


def _decisiones(cliente):
    return [(s, u) for s, u in cliente.calls if not s.startswith("Summarise")]


@pytest.mark.parametrize("brazo", sorted(BRAZOS))
def test_compacta_antes_de_los_pasos_15_30_y_45(brazo):
    cliente = GuionCliente([WAIT] * 50)
    rt = BRAZOS[brazo](cliente, "ESPEC")
    for paso in range(50):
        rt.act(_obs(paso))
    assert rt.compactaciones == [15, 30, 45]
    if brazo.startswith("summary"):
        assert cliente.resumenes == 3


def test_entre_compactaciones_acumula_historia_como_react():
    cliente = GuionCliente([WAIT] * 15)
    rt = FreshLookupRuntime(cliente, "ESPEC")
    for paso in range(15):
        rt.act(_obs(paso))
    _, ultimo = _decisiones(cliente)[-1]
    assert "id=E0" in ultimo and "id=E13" in ultimo and "id=E14" in ultimo


def test_tras_compactar_fresh_lookup_no_ve_historia_previa():
    cliente = GuionCliente([WAIT] * 16)
    rt = FreshLookupRuntime(cliente, "ESPEC")
    for paso in range(16):
        rt.act(_obs(paso))
    _, prompt = _decisiones(cliente)[-1]
    for paso in range(15):
        assert f"id=E{paso}\n" not in prompt and f"id=E{paso} " not in prompt
    assert "id=E15" in prompt
    assert "only via Lookup" in prompt


def test_tras_compactar_summary_ve_el_resumen_y_no_la_historia():
    cliente = GuionCliente([WAIT] * 16)
    rt = SummaryRuntime(cliente, "ESPEC")
    for paso in range(16):
        rt.act(_obs(paso))
    _, prompt = _decisiones(cliente)[-1]
    assert "RESUMEN-1" in prompt
    assert "id=E3\n" not in prompt
    # El resumen se escribe con los pasos que se tiran.
    resumen = [u for s, u in cliente.calls if s.startswith("Summarise")][0]
    assert "id=E0" in resumen and "id=E14" in resumen


def test_hibrido_conserva_sus_lineas_y_reduce_las_observaciones():
    cliente = GuionCliente(["razono PROPIO-0\nAction: Wait({})"] + [WAIT] * 15)
    rt = HybridLookupRuntime(cliente, "ESPEC")
    for paso in range(16):
        rt.act(_obs(paso))
    _, prompt = _decisiones(cliente)[-1]
    assert "razono PROPIO-0" in prompt          # su razonamiento, literal
    assert "id=E0" in prompt                    # la primera linea del evento
    assert "cola0" not in prompt                # la cola del evento, fuera
    assert "cola15" in prompt                   # el evento actual, entero


def test_solo_los_brazos_con_consulta_explican_la_herramienta():
    for brazo, clase in BRAZOS.items():
        cliente = GuionCliente([WAIT])
        clase(cliente, "ESPEC").act(_obs(0))
        system, _ = cliente.calls[0]
        assert ("Lookup: <words>" in system) == brazo.endswith("lookup")
        if brazo.endswith("lookup"):
            assert "only available through lookup" in system


def test_lookup_devuelve_lineas_cronologicas_con_su_paso():
    cliente = GuionCliente(
        [WAIT] * 3 + ["Lookup: shelf=7", 'Action: Store({"shelf": 1, "sku": "A", "units": 1, "lot": "L"})'])
    rt = FreshLookupRuntime(cliente, "ESPEC")
    rt.act(_obs(0, "EVENT inbound | shelf=7 | sku=A"))
    rt.act(_obs(1, "EVENT telemetry | x=1"))
    rt.act(_obs(2, "EVENT correction | SHELF=7 | now=empty"))
    accion, completions = rt.act(_obs(3, "EVENT inbound | sku=B"))
    assert accion.name == "Store"
    assert len(completions) == 2
    _, repregunta = _decisiones(cliente)[-1]
    i0 = repregunta.index("step 0: Observation: [step 0] EVENT inbound | shelf=7")
    i2 = repregunta.index("step 2: Observation: [step 2] EVENT correction | SHELF=7")
    assert i0 < i2
    assert rt.consultas[0].coincidencias == 2
    assert rt.consultas[0].paso == 3


def test_lookup_exige_todas_las_palabras_y_devuelve_las_8_mas_recientes():
    cliente = GuionCliente([WAIT] * 12 + ["Lookup: sku=A inbound", WAIT])
    rt = FreshLookupRuntime(cliente, "ESPEC")
    for paso in range(12):
        rt.act(_obs(paso, f"EVENT inbound | sku=A | n={paso}" if paso % 2 == 0 or paso > 5
                    else f"EVENT outbound | sku=A | n={paso}"))
    rt.act(_obs(12, "EVENT telemetry"))
    consulta = rt.consultas[0]
    assert consulta.coincidencias == 9          # pasos 0, 2, 4 y 6..11
    assert len(consulta.lineas) == 8
    assert consulta.lineas[0].startswith("step 2:")
    assert consulta.lineas[-1].startswith("step 11:")


def test_tope_de_dos_consultas_por_paso():
    cliente = GuionCliente(["Lookup: a", "Lookup: b", "Lookup: c"])
    rt = FreshLookupRuntime(cliente, "ESPEC")
    accion, completions = rt.act(_obs(0))
    assert accion is None
    assert len(completions) == 3                # 2 consultas + la pregunta final
    assert len(rt.consultas) == 2
    assert rt.sin_accion_tras_consultas == 1
    _, ultima = _decisiones(cliente)[-1]
    assert "used your 2 lookups" in ultima


def test_summary_no_consulta_aunque_lo_pida():
    cliente = GuionCliente(["Lookup: algo"])
    rt = SummaryRuntime(cliente, "ESPEC")
    accion, completions = rt.act(_obs(0))
    assert accion is None and len(completions) == 1 and rt.consultas == []


def test_las_completions_auxiliares_se_devuelven_para_contabilidad():
    cliente = GuionCliente([WAIT] * 15 + ["Lookup: id=E3", WAIT])
    rt = SummaryLookupRuntime(cliente, "ESPEC")
    for paso in range(15):
        rt.act(_obs(paso))
    _, completions = rt.act(_obs(15))
    # resumen + consulta + respuesta final
    assert [c.text for c in completions] == ["RESUMEN-1", "Lookup: id=E3", WAIT]


def test_el_transcript_crudo_no_se_compacta():
    cliente = GuionCliente([WAIT] * 46 + ["Lookup: id=E0", WAIT])
    rt = FreshLookupRuntime(cliente, "ESPEC")
    for paso in range(46):
        rt.act(_obs(paso))
    assert rt.compactaciones == [15, 30, 45]
    assert rt.transcript[0] == (0, "Observation: [step 0] EVENT telemetry | id=E0")
    assert sum(1 for p, _ in rt.transcript if p == 0) == 3   # evento (2 lineas) + respuesta
    rt.act(_obs(46))
    assert rt.consultas[0].lineas == ["step 0: Observation: [step 0] EVENT telemetry | id=E0"]


def test_las_consultas_no_entran_en_el_transcript():
    cliente = GuionCliente(["Lookup: id=E0", WAIT, "Lookup: id=E0", WAIT])
    rt = FreshLookupRuntime(cliente, "ESPEC")
    rt.act(_obs(0))
    rt.act(_obs(1))
    # Si los resultados se guardaran, la segunda busqueda encontraria su propio eco.
    assert rt.consultas[1].coincidencias == 1


def test_state_size_es_cero():
    for clase in BRAZOS.values():
        assert clase(GuionCliente([]), "ESPEC").state_size() == 0


def test_pedido_de_consulta_tolera_markdown():
    assert pedido_de_consulta("pienso\n**Lookup:** shelf=12") == "shelf=12"
    assert pedido_de_consulta("`Lookup: SKU-D lot`") == "SKU-D lot"
    assert pedido_de_consulta("Action: Wait({})") is None
    assert palabras_de('"Shelf=12", SKU-D') == ["shelf=12", "sku-d"]
