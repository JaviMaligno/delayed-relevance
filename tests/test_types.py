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
