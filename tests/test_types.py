from dr.types import Observation, Action, StepResult


def test_observation_renders_as_text():
    obs = Observation(step=3, text="incoming pallet of 12 units of SKU-A", actionable=True)
    assert obs.render() == "[step 3] incoming pallet of 12 units of SKU-A"


def test_action_roundtrips_through_string():
    action = Action(name="Store", args={"shelf": 17, "sku": "SKU-A", "qty": 12})
    assert Action.parse(action.render()) == action


def test_action_parse_returns_none_on_garbage():
    assert Action.parse("no soy una accion") is None


def test_step_result_records_correctness():
    result = StepResult(step=1, actionable=True, correct=True, prompt_tokens=100, output_tokens=20)
    assert result.correct is True


def test_action_parse_ignores_an_action_mentioned_in_the_reasoning():
    text = (
        'Reasoning: earlier I did Store({"shelf": 3, "sku": "SKU-A", "qty": 2}).'
        " Now the order arrives.\n"
        'Action: Ship({"shelf": 3, "sku": "SKU-A"})'
    )
    assert Action.parse(text) == Action(name="Ship", args={"shelf": 3, "sku": "SKU-A"})


def test_action_parse_ignores_prose_after_the_action():
    text = (
        "Thinking step by step.\n"
        'Action: Store({"shelf": 0, "sku": "SKU-A", "qty": 1})\n'
        "Note: alternative was Wait({})."
    )
    assert Action.parse(text) == Action(name="Store", args={"shelf": 0, "sku": "SKU-A", "qty": 1})


def test_action_parse_takes_the_last_action_block():
    text = 'Action: Wait({})\nOn reflection:\nAction: Ship({"shelf": 7, "sku": "SKU-B"})'
    assert Action.parse(text) == Action(name="Ship", args={"shelf": 7, "sku": "SKU-B"})


def test_action_parse_without_marker_takes_the_last_command():
    text = 'first Wait({}) then Store({"shelf": 1, "sku": "SKU-C", "qty": 3})'
    assert Action.parse(text) == Action(name="Store", args={"shelf": 1, "sku": "SKU-C", "qty": 3})


def test_reasoning_response_parses_the_same_in_react_and_skillstate():
    """El mismo texto de razonamiento no puede puntuar distinto segun el brazo."""
    from dr.llm import FakeClient
    from dr.runtimes.react import ReActRuntime
    from dr.runtimes.skillstate import SkillStateRuntime
    import json as _json

    reasoning = (
        'I stored SKU-A with Store({"shelf": 3, "sku": "SKU-A", "qty": 2}) earlier.\n'
        'Action: Ship({"shelf": 3, "sku": "SKU-A"})'
    )
    react = ReActRuntime(client=FakeClient(responses=[reasoning]), spec="ESPEC")
    react_action, _ = react.act(Observation(step=0, text="order received for SKU-A", actionable=True))

    payload = _json.dumps({"state_patch": {}, "action": 'Ship({"shelf": 3, "sku": "SKU-A"})'})
    skill = SkillStateRuntime(
        client=FakeClient(responses=[f"razonamiento\n```json\n{payload}\n```"]),
        spec="ESPEC",
        schema_fields=["shelf_contents", "last_event"],
    )
    skill_action, _ = skill.act(Observation(step=0, text="order received for SKU-A", actionable=True))
    assert react_action == skill_action
