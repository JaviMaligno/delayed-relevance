"""Sonda L1 estricta (revision adversarial 6, hallazgo 1).

El generador elegia el ultimo paso en que la estanteria de la cuarentena seria la libre
mas baja y ponia el aviso k pasos antes, sin comprobar que no lo fuera ya en medio: en
la mayoria de las seeds el hecho importaba 5 u 8 pasos despues del aviso. Y el paso
puntuado no siempre dependia del hecho en la trayectoria real.
"""
import copy

import pytest

from dr.envs.warehouse import Warehouse
from dr.llm import Completion
from dr.types import Action


def _dependencias_con_politica_correcta(env):
    env.reset()
    pasos = []
    while not env.done:
        env.observe()
        sin = copy.deepcopy(env)
        sin.quarantined_shelf = None
        if env.expected_action().render() != sin.expected_action().render():
            pasos.append(env.step_index)
        env.apply(env.expected_action())
    return pasos


def test_en_modo_estricto_el_hecho_importa_por_primera_vez_justo_en_t_mas_k():
    encontrados = 0
    for seed in range(12):
        try:
            env = Warehouse(horizon=50, seed=seed, latent_k=40, latent_estricto=True)
        except ValueError:
            continue
        encontrados += 1
        assert env.dependent_step - env.quarantine_from == 40
        deps = _dependencias_con_politica_correcta(env)
        assert deps and deps[0] == env.dependent_step, (seed, deps)
    assert encontrados >= 3


def test_sin_modo_estricto_el_generador_no_cambia():
    # Lo ya medido se hizo asi; el valor por defecto no lo puede mover.
    a = Warehouse(horizon=50, seed=1, latent_k=40)
    assert (a.quarantine_from, a.dependent_step) == (7, 47)


class _MudoHastaElPasoYLuegoEstanteriaCero:
    """Control negativo de la revision: no lee el aviso ni recuerda nada."""
    def __init__(self, env):
        self.env = env

    def act(self, obs):
        if self.env.step_index < self.env.dependent_step:
            return None, [Completion(text="", prompt_tokens=1, output_tokens=0)]
        from dr.envs.warehouse import event_field
        return Action(name="Store", args={"shelf": 0, "sku": event_field(obs.text, "sku") or "",
                                          "units": int(event_field(obs.text, "units") or 0),
                                          "lot": event_field(obs.text, "lot") or ""}), [
            Completion(text="x", prompt_tokens=1, output_tokens=1)]

    def state_size(self):
        return 0


def test_un_agente_que_no_sabe_nada_nunca_suma_un_acierto_que_materialice():
    from experiments.probe_a import run_episode_probe
    for seed in range(12):
        try:
            env = Warehouse(horizon=50, seed=seed, latent_k=40, latent_estricto=True)
        except ValueError:
            continue
        _, acierto, info = run_episode_probe(env, _MudoHastaElPasoYLuegoEstanteriaCero(env))
        assert not (acierto and info["materializa"]), seed
