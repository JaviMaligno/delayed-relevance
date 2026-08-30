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
