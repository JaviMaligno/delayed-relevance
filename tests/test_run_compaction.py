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
