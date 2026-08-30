from dr.envs.warehouse import Warehouse
from dr.llm import FakeClient
from dr.runtimes.react import ReActRuntime
from dr.types import Observation


def test_first_prompt_contains_the_spec_and_the_observation():
    client = FakeClient(responses=['Action: Store({"shelf": 0, "sku": "SKU-A", "qty": 1})'])
    runtime = ReActRuntime(client=client, spec="ESPEC")
    runtime.act(Observation(step=0, text="evento uno", actionable=True))
    system, user = client.calls[0]
    assert "ESPEC" in system
    assert "evento uno" in user


def test_second_prompt_still_contains_the_first_observation():
    client = FakeClient(responses=["Action: Wait({})", "Action: Wait({})"])
    runtime = ReActRuntime(client=client, spec="ESPEC")
    runtime.act(Observation(step=0, text="evento uno", actionable=False))
    runtime.act(Observation(step=1, text="evento dos", actionable=False))
    _, user = client.calls[1]
    assert "evento uno" in user
    assert "evento dos" in user


def test_prompt_grows_with_history():
    client = FakeClient(responses=["Action: Wait({})"] * 3)
    runtime = ReActRuntime(client=client, spec="ESPEC")
    sizes = []
    for step in range(3):
        runtime.act(Observation(step=step, text=f"evento {step}", actionable=False))
        sizes.append(len(client.calls[-1][1]))
    assert sizes[0] < sizes[1] < sizes[2]


def test_returns_the_parsed_action():
    client = FakeClient(responses=['Action: Store({"shelf": 4, "sku": "SKU-B", "qty": 2})'])
    runtime = ReActRuntime(client=client, spec="ESPEC")
    action, _ = runtime.act(Observation(step=0, text="evento", actionable=True))
    assert action.name == "Store"
    assert action.args["shelf"] == 4
