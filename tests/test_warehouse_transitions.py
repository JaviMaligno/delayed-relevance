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
