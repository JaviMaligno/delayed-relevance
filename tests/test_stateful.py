import json

from dr.llm import FakeClient
from dr.runtimes.stateful import StatefulRuntime
from dr.types import Observation


def test_prompt_contains_both_state_and_full_history():
    client = FakeClient(
        responses=[
            'StateUpdate: {"shelf_contents": "0:SKU-A"} Action: Wait({})',
            "Action: Wait({})",
        ]
    )
    runtime = StatefulRuntime(client=client, spec="ESPEC", schema_fields=["shelf_contents"])
    runtime.act(Observation(step=0, text="evento uno", actionable=False))
    runtime.act(Observation(step=1, text="evento dos", actionable=False))
    _, user = client.calls[1]
    assert "evento uno" in user
    assert "0:SKU-A" in user


def test_state_update_is_applied():
    client = FakeClient(responses=['StateUpdate: {"shelf_contents": "7:SKU-C"} Action: Wait({})'])
    runtime = StatefulRuntime(client=client, spec="ESPEC", schema_fields=["shelf_contents"])
    runtime.act(Observation(step=0, text="evento", actionable=False))
    assert runtime.state["shelf_contents"] == "7:SKU-C"


def test_malformed_state_update_leaves_state_untouched():
    client = FakeClient(responses=["StateUpdate: {roto Action: Wait({})"])
    runtime = StatefulRuntime(client=client, spec="ESPEC", schema_fields=["shelf_contents"])
    runtime.act(Observation(step=0, text="evento", actionable=False))
    assert runtime.state == {}


def test_prompt_shows_the_state_schema():
    client = FakeClient(responses=["Action: Wait({})"])
    runtime = StatefulRuntime(
        client=client, spec="ESPEC", schema_fields=["shelf_contents", "last_event"]
    )
    runtime.act(Observation(step=0, text="evento", actionable=False))
    _, user = client.calls[0]
    assert "shelf_contents" in user
    assert "last_event" in user


def test_state_update_outside_the_schema_is_ignored():
    client = FakeClient(responses=['StateUpdate: {"inventado": 1, "shelf_contents": "0:SKU-A"}'])
    runtime = StatefulRuntime(client=client, spec="ESPEC", schema_fields=["shelf_contents"])
    runtime.act(Observation(step=0, text="evento", actionable=False))
    assert runtime.state == {"shelf_contents": "0:SKU-A"}


def test_un_parche_anidado_se_aplica_entero():
    # La regex no codiciosa cortaba el JSON en la primera llave de cierre. Con un
    # parche anidado -- el caso normal en shelf_contents -- el JSON quedaba truncado,
    # no parseaba y el parche se tiraba en silencio: en R2 se aplicaron 0 de 6.000.
    from dr.runtimes.stateful import StatefulRuntime

    rt = StatefulRuntime(client=None, spec="", schema_fields=["shelf_contents", "last_event"])
    rt._apply_state_update(
        'Razono.\nStateUpdate: {"shelf_contents": {"0": {"sku": "SKU-C", "units": 19, '
        '"lot": "L-5179"}}, "last_event": "inbound_pallet"}\n'
        'Action: Store({"shelf": 0, "sku": "SKU-C", "units": 19, "lot": "L-5179"})')
    assert rt.state == {"shelf_contents": {"0": {"sku": "SKU-C", "units": 19, "lot": "L-5179"}},
                        "last_event": "inbound_pallet"}


def test_las_llaves_dentro_de_una_cadena_no_cierran_el_parche():
    from dr.runtimes.stateful import StatefulRuntime

    rt = StatefulRuntime(client=None, spec="", schema_fields=["last_event"])
    rt._apply_state_update('StateUpdate: {"last_event": "nota con } dentro"}\nAction: Wait({})')
    assert rt.state == {"last_event": "nota con } dentro"}
