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


import pytest


@pytest.mark.parametrize("texto", [
    'StateUpdate: {"last_event": "x"}\nAction: Wait({})',
    '**StateUpdate:**\n{"last_event": "x"}\n\n**Action:**\nWait({})',
    '**StateUpdate:**\n```json\n{"last_event": "x"}\n```\n**Action:** Wait({})',
    'StateUpdate:\n```\n{"last_event": "x"}\n```\nAction: Wait({})',
])
def test_el_parche_se_lee_aunque_venga_en_markdown(texto):
    # Haiku escribe a menudo `**StateUpdate:**` y el JSON en un bloque de codigo. El
    # parser v2 exigia la llave justo detras de los dos puntos y tiro 731 de 3.000
    # parches validos en T=200 (revision adversarial 3, hallazgo 1).
    from dr.runtimes.stateful import StatefulRuntime

    rt = StatefulRuntime(client=None, spec="", schema_fields=["last_event"])
    rt._apply_state_update(texto)
    assert rt.state == {"last_event": "x"}


def test_sin_objeto_json_no_se_aplica_nada():
    from dr.runtimes.stateful import StatefulRuntime

    rt = StatefulRuntime(client=None, spec="", schema_fields=["last_event"])
    rt._apply_state_update("StateUpdate: none this step\nAction: Wait({})")
    assert rt.state == {}


class _ClienteQueAnotaPrefijos(FakeClient):
    def __init__(self, responses):
        super().__init__(responses=responses)
        self.prefijos = []

    def complete(self, system, user, max_tokens=None, cache_prefix=None):
        self.prefijos.append(cache_prefix)
        return super().complete(system, user, max_tokens, cache_prefix)


def _dos_pasos(**opciones):
    cliente = _ClienteQueAnotaPrefijos(
        ['StateUpdate: {"last_event": "a"}\nAction: Wait({})',
         'StateUpdate: {"last_event": "b"}\nAction: Wait({})'])
    rt = StatefulRuntime(client=cliente, spec="E", schema_fields=["last_event"], **opciones)
    rt.act(Observation(step=0, text="evento uno", actionable=False))
    rt.act(Observation(step=1, text="evento dos", actionable=False))
    return cliente


def test_por_defecto_no_se_marca_prefijo_cacheable():
    # Lo ya medido se hizo asi; el valor por defecto no puede cambiarlo.
    assert _dos_pasos().prefijos == [None, None]


def test_con_historia_primero_la_historia_es_el_prefijo_y_el_estado_va_detras():
    # Aislar el efecto del orden en el coste (revision adversarial 3, hallazgo 9): los
    # dos ordenes marcan cache; lo unico que cambia es que va primero.
    cliente = _dos_pasos(orden="historia_primero", cachear=True)
    prefijo = "".join(cliente.prefijos[1])
    assert "evento uno" in prefijo and "Current State:" not in prefijo
    assert "Current State:" in cliente.calls[1][1].split(prefijo, 1)[1]


def test_con_estado_primero_y_cache_el_estado_encabeza_el_prefijo():
    cliente = _dos_pasos(orden="estado_primero", cachear=True)
    prefijo = cliente.prefijos[1]
    assert prefijo[0].startswith("Current State:") and '"last_event": "a"' in prefijo[0]
    assert "evento uno" in "".join(prefijo[1:])
