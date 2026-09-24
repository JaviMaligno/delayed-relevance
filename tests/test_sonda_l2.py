"""Sonda L2 (invalidacion retroactiva): la medida tiene que salir de la trayectoria REAL.

Revision adversarial 5, hallazgo 1: el informe calculaba los aciertos como
`dependientes - sordas`, con los dependientes de un agente sordo simulado, y el runner
aplicaba la accion CORRECTA cuando el runtime no devolvia ninguna. Un runtime que nunca
contesta sacaba el 100 %.
"""
from experiments.diagnose_probeC import episodio
from dr.llm import Completion


class _Mudo:
    """Nunca devuelve accion."""
    invalid_patches = 0

    def act(self, obs):
        return None, [Completion(text="", prompt_tokens=1, output_tokens=0)]

    def state_size(self):
        return 0


class _Oraculo:
    """Siempre acierta: devuelve la accion esperada del entorno que se le da."""
    invalid_patches = 0

    def __init__(self, env):
        self.env = env

    def act(self, obs):
        return self.env.expected_action(), [Completion(text="x", prompt_tokens=1, output_tokens=1)]


def test_un_runtime_que_no_contesta_no_puntua():
    # Con la formula vieja sacaba el 100 %. Ahora no acierta ningun paso dependiente y
    # su episodio no cuenta como correccion aplicada.
    for seed in (4, 10, 6):
        d = episodio(None, seed=seed, k=10, runtime="react", fabrica=lambda env: _Mudo())
        assert d["correcta"] == 0
        assert d["primer_dependiente"] != "correcta"


def test_el_oraculo_acierta_el_paso_que_decide_la_correccion():
    # En una trayectoria correcta hay exactamente un paso decisivo por episodio.
    for seed in (4, 10, 6):
        d = episodio(None, seed=seed, k=10, runtime="react", fabrica=_Oraculo)
        assert d["dependientes"] == 1 and d["primer_dependiente"] == "correcta"


def test_un_paso_sin_accion_no_repara_el_mundo():
    # Si el mudo reparase el mundo, el estado real seguiria al ground truth y los
    # dependientes coincidirian con los del oraculo; sin reparar, el mundo del mudo
    # no se mueve y su trayectoria es otra.
    mudo = episodio(None, seed=4, k=10, runtime="react", fabrica=lambda env: _Mudo())
    oraculo = episodio(None, seed=4, k=10, runtime="react", fabrica=_Oraculo)
    assert oraculo["correcta"] == oraculo["dependientes"] > 0
    assert mudo["pasos_con_mundo_distinto"] > 0 and oraculo["pasos_con_mundo_distinto"] == 0


def test_la_sonda_l1_tampoco_repara_el_mundo_en_un_paso_sin_accion():
    # Mismo defecto en probe_a.py: un paso sin accion aplicaba la accion correcta.
    from experiments.probe_a import run_episode_probe
    from dr.envs.warehouse import Warehouse

    env = Warehouse(horizon=50, seed=0, latent_k=40)
    resultados, acierto = run_episode_probe(env, _Mudo())
    assert acierto is False
    assert all(v is None for v in env.shelves.values()), "un mudo no puede llenar el almacen"
