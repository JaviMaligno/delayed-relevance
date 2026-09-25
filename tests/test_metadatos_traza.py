"""La traza tiene que decir bajo que condiciones se midio.

Una revision adversarial encontro que las trazas no guardaban `max_tokens`,
presupuesto de razonamiento, proveedor ni version del modelo, asi que **no se podia
certificar que dos condiciones comparadas usaran el mismo tope de salida** -- que es
exactamente el error que ya se habia cometido una vez, comparando una celda a tope 600
contra otra a 8192.

Tampoco guardaban tokens, asi que la densidad de contexto de una celda medida con el
adjudicador no existia en ningun sitio y hubo que citar la de otra condicion.

Las dos cosas se arreglan en la misma fila: una cabecera con las condiciones, y el uso
de tokens por paso.
"""
import json

from dr.llm import Completion
from dr.runner import run_episode
from dr.types import Action, Observation


class EntornoFalso:
    def __init__(self): self.step_index = 0
    def reset(self): self.step_index = 0
    @property
    def done(self): return self.step_index >= 2
    def observe(self): return Observation(step=self.step_index, text="EVENT x", actionable=True)
    def expected_action(self): return Action(name="Store", args={"shelf": 0})
    def apply(self, accion): self.step_index += 1


class RuntimeFalso:
    def act(self, observation):
        return Action(name="Store", args={"shelf": 0}), [
            Completion(text="Action: Store 0", prompt_tokens=1234, output_tokens=56,
                       cache_read=7, cache_write=9, thinking_tokens=8,
                       model_version="modelo-x-09")]
    def state_size(self): return 0


def test_cada_paso_guarda_su_uso_de_tokens(tmp_path):
    destino = tmp_path / "t.jsonl"
    run_episode(EntornoFalso(), RuntimeFalso(), traza=destino)
    fila = json.loads(destino.read_text().splitlines()[0])
    assert fila["prompt_tokens"] == 1234
    assert fila["output_tokens"] == 56
    assert fila["cache_read"] == 7
    # Sin las escrituras, un brazo que reescribe la cache en cada paso -- el caso mas
    # caro, a 1,25x -- parecia el mas barato: su prompt figuraba con ~540 tokens.
    assert fila["cache_write"] == 9
    assert fila["thinking_tokens"] == 8


def test_cada_paso_guarda_la_version_de_modelo_que_contesto(tmp_path):
    # El §7 del borrador afirmaba que el ID respondido se registra en cada corrida, y
    # no era cierto para las trazas.
    destino = tmp_path / "t.jsonl"
    run_episode(EntornoFalso(), RuntimeFalso(), traza=destino)
    fila = json.loads(destino.read_text().splitlines()[0])
    assert fila["model_version"] == "modelo-x-09"


def test_la_traza_abre_con_una_cabecera_de_condiciones(tmp_path):
    # Sin esto, dos ficheros de la misma celda pueden venir de topes distintos y nada
    # lo dice. La cabecera va como primera fila, marcada, para no romper el conteo de
    # pasos de quien ya lee estos ficheros.
    destino = tmp_path / "t.jsonl"
    run_episode(EntornoFalso(), RuntimeFalso(), traza=destino,
                condiciones={"max_tokens": 8192, "thinking_budget": 0,
                             "provider": "vertex", "apendice_b": True})
    filas = [json.loads(l) for l in destino.read_text().splitlines()]
    assert filas[0]["kind"] == "run_header"
    assert filas[0]["condiciones"]["max_tokens"] == 8192
    assert filas[0]["condiciones"]["provider"] == "vertex"
    assert [f for f in filas if f.get("kind") != "run_header"][0]["step"] == 0


def test_sin_condiciones_no_se_escribe_cabecera(tmp_path):
    # Compatibilidad con las 367 trazas ya medidas, que no la tienen.
    destino = tmp_path / "t.jsonl"
    run_episode(EntornoFalso(), RuntimeFalso(), traza=destino)
    filas = [json.loads(l) for l in destino.read_text().splitlines()]
    assert all(f.get("kind") != "run_header" for f in filas)
    assert len(filas) == 2
