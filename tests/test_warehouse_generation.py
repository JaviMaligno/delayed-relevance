from dr.envs.warehouse import Warehouse


def test_same_seed_gives_same_event_sequence():
    a = [Warehouse(horizon=10, seed=7).script[i].text for i in range(10)]
    b = [Warehouse(horizon=10, seed=7).script[i].text for i in range(10)]
    assert a == b


def test_different_seed_gives_different_sequence():
    a = [Warehouse(horizon=10, seed=7).script[i].text for i in range(10)]
    b = [Warehouse(horizon=10, seed=8).script[i].text for i in range(10)]
    assert a != b


def test_script_has_exactly_horizon_events():
    assert len(Warehouse(horizon=25, seed=1).script) == 25


def test_first_event_is_always_a_store():
    # No se puede pedir un envio antes de haber almacenado nada.
    assert Warehouse(horizon=10, seed=3).script[0].text.startswith("incoming pallet")


def test_shelf_count_is_500():
    assert len(Warehouse(horizon=10, seed=1).shelves) == 500


def _canonical_orders(horizon: int, seed: int):
    """Recorre la trayectoria de ground truth y devuelve (ordenes, ordenes sin stock)."""
    env = Warehouse(horizon=horizon, seed=seed)
    env.reset()
    orders = unsatisfiable = 0
    while not env.done:
        observation = env.observe()
        if observation.text.startswith("order received"):
            orders += 1
            if env.expected_action().name == "Wait":
                unsatisfiable += 1
        env.apply(env.expected_action())
    return orders, unsatisfiable


def test_every_order_is_satisfiable_on_the_canonical_trajectory():
    # Un envio cuyo SKU ya no esta en stock tiene ground truth Wait, y esa regla
    # el modelo no puede deducirla de P: seria un suelo de accuracy no documentado.
    for seed in range(5):
        orders, unsatisfiable = _canonical_orders(horizon=100, seed=seed)
        assert orders > 0
        assert unsatisfiable == 0


def test_spec_documents_what_to_do_with_an_unstocked_order():
    assert "not currently in stock" in Warehouse(horizon=10, seed=1).spec()
