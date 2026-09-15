"""El hueco 3 de I4: nuestra telemetria no es su Env 1, es su Experimento 2.

Su Algoritmo 2 no tiene familia no accionable: `possible_events = [Receive]`, y si
hay estanterias ocupadas anade `Order` y `Maintenance`. **Todos sus pasos exigen
decision.** El ruido del Apendice C es otra cosa: se **anexa** a la observacion de un
evento real bajo una cabecera `--- BACKGROUND TELEMETRY ---`, es explicitamente
`Non-State-Altering`, y solo aparece en su Experimento 2.

Nuestro entorno mete telemetria como **paso propio** en un tercio de los pasos. Eso
hace que un tercio de la historia no mute el estado: crece el transcript, pero hay
menos que recordar. Es la ultima hipotesis viva para la unica discrepancia que queda
en pie tras R1 y tras el Apendice B -- que su ReAct pierda 26 puntos y el nuestro 1.

Dos banderas independientes, para poder medir el peso de cada mitad:
  `sin_telemetria` -> el generador de su Algoritmo 2, todos los pasos accionables.
  `ruido=N`        -> N lineas de distractor anexadas a cada observacion.
"""
from dr.envs.warehouse import Warehouse
from dr.types import Action

CABECERA = "--- BACKGROUND TELEMETRY ---"


def test_sin_telemetria_no_deja_ningun_evento_de_telemetria():
    env = Warehouse(horizon=60, seed=5, sin_telemetria=True)
    assert not any("EVENT telemetry" in o.text for o in env.script)


def test_sin_telemetria_todos_los_pasos_son_accionables():
    # Su Algoritmo 2 no tiene rama no accionable. Si nos sobra un tercio de pasos
    # sin decision, el denominador del score no es el suyo y la carga de memoria por
    # paso tampoco.
    env = Warehouse(horizon=60, seed=5, sin_telemetria=True)
    assert all(o.actionable for o in env.script)


def test_por_defecto_sigue_habiendo_pasos_no_accionables():
    # La linea base son 100 episodios ya pagados: no puede cambiar por debajo.
    env = Warehouse(horizon=60, seed=5)
    assert any(not o.actionable for o in env.script)


def test_el_ruido_se_anexa_bajo_su_cabecera_y_no_como_paso_propio():
    env = Warehouse(horizon=20, seed=2, sin_telemetria=True, ruido=3)
    obs = env.script[0]
    assert CABECERA in obs.text
    assert obs.text.index("EVENT") < obs.text.index(CABECERA), "el evento va primero"
    cola = obs.text.split(CABECERA)[1].strip().splitlines()
    assert len([l for l in cola if l.strip()]) == 3


def test_el_ruido_no_altera_el_estado_ni_la_accion_esperada():
    # "Non-State-Altering": si el ruido cambiara la accion correcta, no seria ruido.
    limpio = Warehouse(horizon=20, seed=2, sin_telemetria=True)
    ruidoso = Warehouse(horizon=20, seed=2, sin_telemetria=True, ruido=5)
    limpio.reset(); ruidoso.reset()
    while not limpio.done:
        a, b = limpio.expected_action(), ruidoso.expected_action()
        assert (a.name, a.args) == (b.name, b.args)
        limpio.apply(a); ruidoso.apply(b)


def test_el_ruido_se_regenera_en_cada_paso():
    # "sampled uniformly at random during each execution step": un bloque identico
    # en todos los pasos se comprime solo y deja de distraer.
    env = Warehouse(horizon=20, seed=2, sin_telemetria=True, ruido=4)
    colas = [o.text.split(CABECERA)[1] for o in env.script]
    assert len(set(colas)) > 1


def test_sin_ruido_no_aparece_la_cabecera():
    env = Warehouse(horizon=20, seed=2, sin_telemetria=True)
    assert all(CABECERA not in o.text for o in env.script)


def test_el_procedimiento_deja_de_prometer_telemetria():
    # Decirle al agente que existe un tipo de evento que ya no llega es una pista
    # falsa, y ademas gasta contexto.
    spec = Warehouse(horizon=20, seed=2, sin_telemetria=True).spec()
    assert "telemetry" not in spec.lower()


def test_el_guion_sigue_siendo_determinista_por_seed():
    a = [o.text for o in Warehouse(horizon=40, seed=7, sin_telemetria=True, ruido=3).script]
    b = [o.text for o in Warehouse(horizon=40, seed=7, sin_telemetria=True, ruido=3).script]
    assert a == b


def test_las_dos_banderas_juntas_dan_el_algoritmo_2():
    # Receive siempre; Order y Maintenance en cuanto hay stock. Nada mas.
    env = Warehouse(horizon=80, seed=11, sin_telemetria=True, apendice_b=True)
    tipos = {t.split()[1] for t in (o.text for o in env.script) for t in [t]}
    familias = {o.text.split("EVENT ")[1].split()[0] for o in env.script}
    assert familias == {"inbound_pallet", "outbound_order", "maintenance_required"}
    assert all(o.actionable for o in env.script)
