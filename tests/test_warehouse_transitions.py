from dr.envs.warehouse import Warehouse
from dr.types import Action


def test_store_expects_first_empty_shelf():
    env = Warehouse(horizon=5, seed=3)
    env.reset()
    expected = env.expected_action()
    assert expected.name == "Store"
    assert expected.args["shelf"] == 0


def test_store_places_stock_on_the_shelf_the_agent_chose():
    env = Warehouse(horizon=5, seed=3)
    env.reset()
    sku = env.observe().text.split()[-1]
    env.apply(Action(name="Store", args={"shelf": 42, "sku": sku, "qty": 5}))
    assert env.shelves[42] == (sku, 5)


def test_ship_expects_a_shelf_that_actually_holds_the_sku():
    # La accion correcta de Ship depende de donde puso el agente la mercancia,
    # no de una posicion fija: esa es la demanda de memoria que mide el entorno.
    env = Warehouse(horizon=30, seed=11)
    env.reset()
    sku = env.observe().text.split()[-1]
    env.apply(Action(name="Store", args={"shelf": 99, "sku": sku, "qty": 5}))
    assert env.shelves[99] == (sku, 5)
    while not env.done and not env.observe().text.startswith("order received"):
        env.apply(env.expected_action())
    if not env.done:
        expected = env.expected_action()
        ordered_sku = env.observe().text.split()[-1]
        assert env.shelves[expected.args["shelf"]][0] == ordered_sku


def test_non_actionable_event_expects_wait():
    env = Warehouse(horizon=40, seed=5)
    env.reset()
    while not env.done and env.observe().actionable:
        env.apply(env.expected_action())
    if not env.done:
        assert env.expected_action().name == "Wait"


def test_done_after_horizon():
    env = Warehouse(horizon=3, seed=1)
    env.reset()
    for _ in range(3):
        env.apply(env.expected_action())
    assert env.done is True


def _first_order_step(env) -> int:
    for index, observation in enumerate(env.script):
        if observation.text.startswith("order received"):
            return index
    raise AssertionError("el guion no contiene ninguna orden")


def test_ship_expects_the_lowest_numbered_shelf_holding_the_sku():
    # Con dos estanterias validas el desempate no puede ser un accidente del orden
    # de iteracion: es una regla que P declara y el agente puede seguir.
    env = Warehouse(horizon=40, seed=11)
    env.reset()
    index = _first_order_step(env)
    env.step_index = index
    sku = env.observe().text.split()[-1]
    # El diccionario se construye en orden inverso a proposito: la respuesta no
    # puede depender del orden de iteracion, solo del numero de estanteria.
    env.shelves = {i: None for i in reversed(range(500))}
    env.shelves[7] = (sku, 4)
    env.shelves[3] = (sku, 9)
    expected = env.expected_action()
    assert expected.name == "Ship"
    assert expected.args["shelf"] == 3


def test_spec_declares_the_tie_break_rule_for_ship():
    assert "lowest-numbered" in Warehouse(horizon=10, seed=1).spec().split("Ship(")[1]


def _stocked_env() -> Warehouse:
    env = Warehouse(horizon=10, seed=3)
    env.reset()
    env.shelves[0] = ("SKU-A", 5)
    env.shelves[1] = ("SKU-B", 7)
    return env


def test_move_out_of_range_is_a_no_op_and_keeps_500_shelves():
    env = _stocked_env()
    before = dict(env.shelves)
    env.apply(Action(name="Move", args={"from": 9999, "to": -3}))
    assert len(env.shelves) == 500
    assert env.shelves == before


def test_move_to_an_occupied_shelf_does_not_destroy_stock():
    env = _stocked_env()
    env.apply(Action(name="Move", args={"from": 0, "to": 1}))
    assert env.shelves[1] == ("SKU-B", 7)
    assert env.shelves[0] == ("SKU-A", 5)


def test_move_from_an_empty_shelf_is_a_no_op():
    env = _stocked_env()
    env.apply(Action(name="Move", args={"from": 250, "to": 251}))
    assert env.shelves[251] is None


def test_move_relocates_stock_when_it_is_valid():
    env = _stocked_env()
    env.apply(Action(name="Move", args={"from": 0, "to": 300}))
    assert env.shelves[300] == ("SKU-A", 5)
    assert env.shelves[0] is None
    assert len(env.shelves) == 500
