import pytest
"""Corredor y precheck de compactacion, sin modelo."""
from dr.llm import Completion
from dr.runtimes.compaction import FreshLookupRuntime
from experiments.precheck_compaction import Perfecto, Politica, geometria
from experiments.run_compaction import construir_env, episodio


class Guion:
    """Consulta el aviso de correccion en el paso 20 y si no, espera."""

    def __init__(self):
        self.n = 0

    def complete(self, system, user, max_tokens=None, cache_prefix=None):
        self.n += 1
        prompt = "".join(cache_prefix or []) + user
        texto = ("Lookup: correction_notice" if "[step 20]" in user and "Your lookup" not in user
                 else "Action: Wait({})")
        return Completion(text=texto, prompt_tokens=len(prompt) // 4, output_tokens=5,
                          cache_read=7, cost_usd=0.001, segundos=0.5)


def test_el_agente_perfecto_saca_el_techo_en_las_dos_sondas():
    for sonda, seed, k in (("C", 4, 10), ("A", 3, 40)):
        env = construir_env(sonda, seed, k)
        d = episodio(env, Perfecto(env), sonda)
        assert d["score"] == 1.0 and d["aciertos"] == d["dependientes"] == 1


def test_el_sordo_falla_toda_la_cascada_de_la_sonda_c():
    env = construir_env("C", 4, 10)
    d = episodio(env, Politica(olvida=False, oye_avisos=False), "C")
    assert (d["aciertos"], d["dependientes"]) == (0, 11)


def test_episodio_cuenta_consultas_portantes_coste_y_llamadas(tmp_path):
    env = construir_env("C", 4, 10)
    traza = tmp_path / "t.jsonl"
    d = episodio(env, FreshLookupRuntime(Guion(), env.spec()), "C", traza, {"x": 1})
    assert d["compactaciones"] == [15, 30, 45]
    assert d["consultas"] == 1 and d["pasos_con_consulta"] == 1
    assert d["consultas_portantes"] == 1 and d["consultas_tras_aviso"] == 1
    assert d["llamadas"] == 51
    assert abs(d["coste_lista_usd"] - 0.051) < 1e-9
    assert d["cache_read"] == 7 * 51
    assert len(traza.read_text(encoding="utf-8").splitlines()) == 51


def test_geometria_de_la_sonda_a_tiene_compactaciones_de_por_medio():
    g = geometria("A", 3, 40)
    assert g["aviso"] == 6 and g["dependientes"] == [46]
    assert g["entre"][46] == [15, 30, 45]


def test_cache_ideal_estima_el_prefijo_comun_con_la_llamada_anterior_del_mismo_system():
    from experiments.run_compaction import ConCacheIdeal, entrada_estimada

    class Fijo:
        provider = "x"

        def complete(self, system, user, max_tokens=None, cache_prefix=None):
            return Completion(text="", prompt_tokens=100, output_tokens=1)

    c = ConCacheIdeal(Fijo())
    primera = c.complete("S", "aaaa", cache_prefix=["H\n"])
    otra = c.complete("Summarise", "zzzz")                 # otro system: no rompe la cadena
    segunda = c.complete("S", "bbbb", cache_prefix=["H\n", "aaaa\n"])
    assert primera.cache_ideal == 0 and otra.cache_ideal == 0
    texto = "S\nH\naaaa\nbbbb"
    assert segunda.cache_ideal == round(100 * len("S\nH\naaaa") / len(texto))
    esperada = segunda.cache_ideal * 0.1 + (100 - segunda.cache_ideal) * 1.25
    assert entrada_estimada(segunda) == esperada


def test_episodio_guarda_el_texto_de_las_consultas():
    env = construir_env("C", 4, 10)
    d = episodio(env, FreshLookupRuntime(Guion(), env.spec()), "C")
    assert d["textos_consulta"] == ["correction_notice"]
    assert d["truncadas_decision"] == 0 and d["salida_max_llamada"] == 5


def test_la_configuracion_elegida_de_la_sonda_c_pone_una_compactacion_de_por_medio():
    from experiments.barrido_sonda_c import evaluar
    for seed in (17, 6, 10):
        r = evaluar(seed, 14)
        assert r["valida"] and r["aviso"] == 14 and r["compactacion"] == 15
        assert r["decisivo"] >= 15


def test_aviso_declarado_solo_cambia_el_spec_y_no_el_guion():
    from experiments.run_compaction import construir_env
    base = construir_env("C", 17, 14)
    decl = construir_env("C", 17, 14, aviso_declarado=True)
    assert "correction_notice" not in base.spec()
    assert "correction_notice - an audit finding" in decl.spec()
    assert [o.text for o in base.script] == [o.text for o in decl.script]
    assert base.invalidation_from == decl.invalidation_from


@pytest.mark.parametrize("seed", [17, 6, 10])
def test_aviso_coherente_corrige_el_pale_que_hay_y_no_cambia_lo_medido(seed):
    from experiments.run_compaction import construir_env
    base = construir_env("C", seed, 14)
    coh = construir_env("C", seed, 14, aviso_coherente=True)
    t = coh.invalidation_from
    assert t == base.invalidation_from and coh.invalidated_shelf == base.invalidated_shelf
    aviso = coh.script[t].text
    # Corrige la ultima colocacion en esa estanteria, y nombra el pale que hay en ella.
    paso = int(aviso.split("corrects_step=")[1].split()[0])
    colocado = coh.script[paso].text
    assert "inbound_pallet" in colocado
    for campo in ("pallet_id", "sku", "lot"):
        valor = colocado.split(f"{campo}=")[1].split()[0]
        assert f"{campo}={valor}" in aviso
    assert coh._ocupante_canonico(coh.invalidated_shelf, t) is not None
    # Solo cambia el texto del aviso: el resto del guion, identico.
    assert [o.text for i, o in enumerate(base.script) if i != t] == \
           [o.text for i, o in enumerate(coh.script) if i != t]
