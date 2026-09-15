"""Los dos huecos que I4 encontro, detras de una bandera.

`docs/fidelidad-entorno.md` coteja nuestro Warehouse con su Apendice B y deja dos
diferencias que pueden explicar por que su ReAct pierde 26 puntos en 200 pasos y el
nuestro ninguno:

1. **`Move` nunca se ejerce**, porque no generamos eventos de mantenimiento. Es la
   unica accion que cruza dos partes del estado en un solo paso -- donde esta la
   pieza y que hueco esta libre -- y por tanto donde un transcript acumulado deberia
   estorbar mas que un estado explicito.
2. **Una accion invalida no se rechaza: se aplica.** Ellos rechazan la transicion y
   devuelven una observacion de error local; nosotros sobrescribimos en silencio.

Van detras de `apendice_b=False` y no por debajo: cambiar el entorno sin bandera
invalidaria de golpe los 100 episodios de R1 y dejaria el proyecto sin linea base.
La bandera permite correr las dos variantes, y la diferencia entre ellas **es** la
medida de cuanto pesaba el hueco.
"""
from dr.envs.warehouse import SHELF_COUNT, Warehouse


def _guion(**kwargs) -> list[str]:
    return [o.text for o in Warehouse(horizon=40, seed=3, **kwargs).script]


def test_sin_la_bandera_el_guion_es_identico_byte_a_byte_al_de_antes():
    """Los hashes salen del `warehouse.py` anterior a la bandera (git HEAD del commit
    de R1). La linea base son 100 episodios ya pagados y 178 $ de API: si el guion
    cambia aunque sea en un campo, dejan de ser comparables con lo que corra despues,
    y eso no puede depender de que alguien se acuerde de mirarlo."""
    import hashlib

    for horizonte, seed, esperado in ((40, 3, "6605fba19fbe7a63"),
                                      (200, 0, "e51f4de7a546d2e5")):
        guion = "".join(o.text for o in Warehouse(horizon=horizonte, seed=seed).script)
        assert hashlib.sha256(guion.encode()).hexdigest()[:16] == esperado, (
            f"el guion de T={horizonte} seed={seed} ha cambiado")


def test_sin_la_bandera_no_hay_eventos_de_mantenimiento():
    # Ojo: la telemetria ya traia un campo `maintenance_window`, asi que buscar
    # "maintenance" a secas da un falso positivo. Lo que no puede aparecer es el tipo.
    assert not any("maintenance_required" in t for t in _guion())


def test_con_la_bandera_el_guion_pide_mantenimiento():
    assert any("maintenance_required" in t for t in _guion(apendice_b=True))


def test_el_guion_con_bandera_sigue_siendo_determinista_por_seed():
    assert _guion(apendice_b=True) == _guion(apendice_b=True)


def test_un_evento_de_mantenimiento_es_accionable():
    # Si no entra en el denominador del score, la accion que mas nos interesa no se
    # mide: los fallos en ella saldrian gratis.
    env = Warehouse(horizon=40, seed=3, apendice_b=True)
    mantenimientos = [o for o in env.script if "maintenance_required" in o.text]
    assert mantenimientos and all(o.actionable for o in mantenimientos)


def test_el_mantenimiento_se_resuelve_moviendo_a_la_libre_mas_baja():
    env = Warehouse(horizon=40, seed=3, apendice_b=True)
    env.reset()
    while not env.done:
        obs = env.observe()
        esperada = env.expected_action()
        if "maintenance_required" in obs.text and esperada.name == "Move":
            origen = esperada.args["from"]
            assert env.shelves[origen] is not None, "mueve una estanteria ocupada"
            assert env.shelves[esperada.args["to"]] is None, "mueve a una libre"
            assert esperada.args["to"] == min(
                i for i in range(SHELF_COUNT)
                if env.shelves[i] is None and i != origen), "la libre mas baja"
            return
        env.apply(esperada)
    raise AssertionError("el guion no llego a pedir un Move")


def test_con_bandera_un_store_sobre_estanteria_ocupada_no_cambia_el_estado():
    env = Warehouse(horizon=10, seed=1, apendice_b=True)
    env.reset()
    from dr.types import Action
    env.apply(Action(name="Store", args={"shelf": 0, "sku": "A", "units": 1, "lot": "L-1"}))
    env.apply(Action(name="Store", args={"shelf": 0, "sku": "B", "units": 2, "lot": "L-2"}))
    assert env.shelves[0][0] == "A", "la segunda tiene que rechazarse, no sobrescribir"


def test_sin_bandera_un_store_sobre_ocupada_sigue_sobrescribiendo():
    # Documenta la linea base tal cual es. No es lo que queremos, es lo que medimos.
    env = Warehouse(horizon=10, seed=1)
    env.reset()
    from dr.types import Action
    env.apply(Action(name="Store", args={"shelf": 0, "sku": "A", "units": 1, "lot": "L-1"}))
    env.apply(Action(name="Store", args={"shelf": 0, "sku": "B", "units": 2, "lot": "L-2"}))
    assert env.shelves[0][0] == "B"


def test_el_rechazo_se_le_dice_al_agente_en_la_siguiente_observacion():
    # Su Apendice B devuelve "a local error observation". Sin decirselo, el agente no
    # puede corregir y el rechazo solo seria una penalizacion invisible.
    env = Warehouse(horizon=10, seed=1, apendice_b=True)
    env.reset()
    from dr.types import Action
    env.apply(Action(name="Store", args={"shelf": 0, "sku": "A", "units": 1, "lot": "L-1"}))
    env.apply(Action(name="Store", args={"shelf": 0, "sku": "B", "units": 2, "lot": "L-2"}))
    assert "REJECTED" in env.observe().text


def test_con_bandera_un_ship_de_una_estanteria_que_no_tiene_el_sku_se_rechaza():
    env = Warehouse(horizon=10, seed=1, apendice_b=True)
    env.reset()
    from dr.types import Action
    env.apply(Action(name="Store", args={"shelf": 0, "sku": "A", "units": 1, "lot": "L-1"}))
    env.apply(Action(name="Ship", args={"shelf": 0, "sku": "OTRO"}))
    assert env.shelves[0] is not None, "no puede vaciar una estanteria que no tiene ese SKU"


def test_el_procedimiento_explica_las_dos_reglas_nuevas():
    # Medir contra una regla que el agente no puede conocer no mide memoria: mide
    # adivinanza.
    spec = Warehouse(horizon=10, seed=1, apendice_b=True).spec()
    assert "maintenance_required" in spec
    assert "Move" in spec and "rejected" in spec.lower()


def test_sin_bandera_el_procedimiento_no_menciona_el_mantenimiento():
    assert "maintenance_required" not in Warehouse(horizon=10, seed=1).spec()
