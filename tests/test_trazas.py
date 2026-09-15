"""Sin la respuesta cruda, un score no se puede adjudicar.

El corredor guardaba por paso el booleano `correct` y los contadores de tokens, y
tiraba `completion.text`. Con eso se puede decir que una seed saco 0.83, pero no si
perdio la cuenta del estado -- que es lo que el experimento mide -- o si copio mal
`units` en un JSON de cuatro campos, que es una diferencia NUESTRA contra su accion
posicional de dos (hueco 4 de I4) y cuenta como fallo identico.

Esa distincion decide como se lee la tabla entera, asi que la respuesta completa se
guarda y se guarda siempre, no solo cuando a alguien se le ocurre diagnosticar.
"""
import json

from dr.runner import run_episode
from dr.llm import Completion
from dr.types import Action, Observation


class EntornoFalso:
    """Dos pasos accionables, con una accion esperada fija."""

    def __init__(self):
        self.step_index = 0
        self.aplicadas = []

    def reset(self): self.step_index = 0
    @property
    def done(self): return self.step_index >= 2
    def observe(self):
        return Observation(step=self.step_index, text="EVENT x", actionable=True)
    def expected_action(self):
        return Action(name="Store", args={"shelf": 0})
    def apply(self, action):
        self.aplicadas.append(action)
        self.step_index += 1


class RuntimeFalso:
    """Primer paso acierta; segundo devuelve algo que no parsea."""

    def __init__(self, textos):
        self.textos = list(textos)
        self.n = 0

    def act(self, observation):
        texto = self.textos[self.n]; self.n += 1
        completion = Completion(text=texto, prompt_tokens=10, output_tokens=5)
        accion = Action(name="Store", args={"shelf": 0}) if "Store" in texto else None
        return accion, [completion]

    def state_size(self): return 0


def test_cada_paso_guarda_la_respuesta_completa():
    env, rt = EntornoFalso(), RuntimeFalso(["Action: Store 0", "me he liado"])
    resultados = run_episode(env, rt)
    assert [r.raw for r in resultados] == [("Action: Store 0",), ("me he liado",)]


def test_un_fallo_de_parseo_guarda_el_texto_que_no_parseo():
    # Es el caso que mas importa: sin el texto, un fallo de formato y uno de estado
    # son el mismo cero.
    env, rt = EntornoFalso(), RuntimeFalso(["no hay accion aqui", "Action: Store 0"])
    resultados = run_episode(env, rt)
    assert resultados[0].correct is False
    assert resultados[0].raw == ("no hay accion aqui",)


def test_se_guarda_lo_esperado_y_lo_hecho_para_poder_adjudicar():
    env, rt = EntornoFalso(), RuntimeFalso(["Action: Store 0", "me he liado"])
    resultados = run_episode(env, rt)
    assert resultados[0].esperado == 'Store({"shelf": 0})'
    assert resultados[0].ejecutado == 'Store({"shelf": 0})'
    assert resultados[1].ejecutado is None, "no hubo accion que ejecutar"


def test_la_traza_se_escribe_como_jsonl_con_una_fila_por_paso(tmp_path):
    destino = tmp_path / "traza.jsonl"
    env, rt = EntornoFalso(), RuntimeFalso(["Action: Store 0", "me he liado"])
    run_episode(env, rt, traza=destino)
    filas = [json.loads(l) for l in destino.read_text().splitlines() if l.strip()]
    assert len(filas) == 2
    assert filas[0]["raw"] == {"respuestas": ["Action: Store 0"]}
    assert filas[0]["http"] == 200, "sin esto el lector de la casa descarta la fila"
    assert filas[1]["correct"] is False
    assert filas[1]["esperado"] == 'Store({"shelf": 0})'


def test_la_traza_se_anexa_y_no_pisa_lo_anterior(tmp_path):
    # Una rejilla escribe muchos episodios en el mismo fichero; si cada uno lo abre
    # en modo escritura, al final solo queda el ultimo.
    destino = tmp_path / "traza.jsonl"
    for _ in range(2):
        run_episode(EntornoFalso(), RuntimeFalso(["Action: Store 0", "x"]), traza=destino)
    assert len(destino.read_text().strip().splitlines()) == 4


def test_sin_destino_no_escribe_nada_y_sigue_devolviendo_resultados(tmp_path):
    resultados = run_episode(EntornoFalso(), RuntimeFalso(["Action: Store 0", "x"]))
    assert len(resultados) == 2
    assert not list(tmp_path.iterdir())
