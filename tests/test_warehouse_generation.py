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
    assert Warehouse(horizon=10, seed=3).script[0].text.startswith("EVENT inbound_pallet")


def test_shelf_count_is_500():
    assert len(Warehouse(horizon=10, seed=1).shelves) == 500


def _canonical_orders(horizon: int, seed: int):
    """Recorre la trayectoria de ground truth y devuelve (ordenes, ordenes sin stock)."""
    env = Warehouse(horizon=horizon, seed=seed)
    env.reset()
    orders = unsatisfiable = 0
    while not env.done:
        observation = env.observe()
        if observation.text.startswith("EVENT outbound_order"):
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


def test_latent_rule_moves_only_the_notice_not_the_dependent_step():
    # k es la variable controlada: el paso dependiente y la estanteria no cambian.
    envs = {k: Warehouse(horizon=50, seed=0, latent_k=k) for k in (1, 5, 10, 20, 40)}
    assert len({e.dependent_step for e in envs.values()}) == 1
    assert len({e.quarantined_shelf for e in envs.values()}) == 1
    for k, e in envs.items():
        assert e.dependent_step - e.quarantine_from == k


def test_latent_notice_is_not_actionable_when_it_arrives():
    e = Warehouse(horizon=50, seed=0, latent_k=20)
    assert e.script[e.quarantine_from].actionable is False
    assert "facility_notice" in e.script[e.quarantine_from].text


def test_latent_rule_changes_the_expected_action_but_the_control_does_not():
    from dr.types import Action

    def accion_en_el_paso_dependiente(**kw):
        e = Warehouse(horizon=50, seed=0, **kw)
        e.reset()
        objetivo = e.dependent_step
        while not e.done:
            exp = e.expected_action()
            if e.step_index == objetivo:
                return exp
            e.apply(exp)
        return None

    real = accion_en_el_paso_dependiente(latent_k=20)
    control = accion_en_el_paso_dependiente(latent_k=20, latent_control=True)
    assert real.args["shelf"] != control.args["shelf"]
    assert real.args["shelf"] == control.args["shelf"] + 1


def test_quarantine_is_not_active_before_the_notice_arrives():
    e = Warehouse(horizon=50, seed=0, latent_k=20)
    e.step_index = e.quarantine_from - 1
    assert e._is_quarantined(e.quarantined_shelf) is False
    e.step_index = e.quarantine_from
    assert e._is_quarantined(e.quarantined_shelf) is True
