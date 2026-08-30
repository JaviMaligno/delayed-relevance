import json

from dr.llm import FakeClient
from dr.runtimes.skillstate import SkillStateRuntime
from dr.types import Observation


def _patch(patch: dict, action: str = 'Wait({})') -> str:
    body = json.dumps({"state_patch": patch, "action": action})
    return f"razonamiento intermedio\n```json\n{body}\n```"


def test_prompt_never_contains_previous_observations():
    client = FakeClient(responses=[_patch({"a": 1}), _patch({"b": 2})])
    runtime = SkillStateRuntime(client=client, spec="ESPEC", schema_fields=["a", "b"])
    runtime.act(Observation(step=0, text="evento uno", actionable=False))
    runtime.act(Observation(step=1, text="evento dos", actionable=False))
    _, user = client.calls[1]
    assert "evento dos" in user
    assert "evento uno" not in user


def test_prompt_never_contains_previous_reasoning():
    client = FakeClient(responses=[_patch({"a": 1}), _patch({"b": 2})])
    runtime = SkillStateRuntime(client=client, spec="ESPEC", schema_fields=["a", "b"])
    runtime.act(Observation(step=0, text="evento uno", actionable=False))
    runtime.act(Observation(step=1, text="evento dos", actionable=False))
    _, user = client.calls[1]
    assert "razonamiento intermedio" not in user


def test_patch_merges_into_state():
    client = FakeClient(responses=[_patch({"a": 1}), _patch({"b": 2})])
    runtime = SkillStateRuntime(client=client, spec="ESPEC", schema_fields=["a", "b"])
    runtime.act(Observation(step=0, text="uno", actionable=False))
    runtime.act(Observation(step=1, text="dos", actionable=False))
    assert runtime.state == {"a": 1, "b": 2}


def test_null_deletes_the_key():
    client = FakeClient(responses=[_patch({"a": 1}), _patch({"a": None})])
    runtime = SkillStateRuntime(client=client, spec="ESPEC", schema_fields=["a"])
    runtime.act(Observation(step=0, text="uno", actionable=False))
    runtime.act(Observation(step=1, text="dos", actionable=False))
    assert runtime.state == {}


def test_invalid_patch_triggers_retry_without_corrupting_state():
    client = FakeClient(responses=["esto no es json", _patch({"a": 1})])
    runtime = SkillStateRuntime(client=client, spec="ESPEC", schema_fields=["a"])
    runtime.act(Observation(step=0, text="uno", actionable=False))
    assert runtime.state == {"a": 1}
    assert runtime.invalid_patches == 1


def test_prompt_size_is_flat_across_steps():
    client = FakeClient(responses=[_patch({"a": 1})] * 5)
    runtime = SkillStateRuntime(client=client, spec="ESPEC", schema_fields=["a"])
    for step in range(5):
        runtime.act(Observation(step=step, text="evento", actionable=False))
    sizes = [len(call[1]) for call in client.calls]
    assert max(sizes) - min(sizes) < 40
