import json

from dr.envs.warehouse import Warehouse
from dr.llm import FakeClient
from dr.runner import run_episode
from dr.runtimes.skillstate import SkillStateRuntime


def _patch_response(action_text: str) -> str:
    body = json.dumps({"state_patch": {}, "action": action_text})
    return f"pienso\n```json\n{body}\n```"


def test_runner_produces_one_result_per_step():
    env = Warehouse(horizon=4, seed=2)
    client = FakeClient(responses=[_patch_response("Wait({})")] * 4)
    runtime = SkillStateRuntime(client=client, spec=env.spec(), schema_fields=env.schema_fields())
    results = run_episode(env, runtime)
    assert len(results) == 4


def test_runner_marks_correct_actions():
    env = Warehouse(horizon=4, seed=2)
    correct = []
    probe = Warehouse(horizon=4, seed=2)
    probe.reset()
    for _ in range(4):
        correct.append(probe.expected_action().render())
        probe.apply(probe.expected_action())
    client = FakeClient(responses=[_patch_response(text) for text in correct])
    runtime = SkillStateRuntime(client=client, spec=env.spec(), schema_fields=env.schema_fields())
    results = run_episode(env, runtime)
    assert all(result.correct for result in results)


def test_runner_marks_wrong_actions():
    env = Warehouse(horizon=3, seed=2)
    client = FakeClient(responses=[_patch_response('Ship({"shelf": 499, "sku": "SKU-Z"})')] * 3)
    runtime = SkillStateRuntime(client=client, spec=env.spec(), schema_fields=env.schema_fields())
    results = run_episode(env, runtime)
    assert results[0].correct is False


def test_runner_records_token_usage():
    env = Warehouse(horizon=2, seed=2)
    client = FakeClient(responses=[_patch_response("Wait({})")] * 2)
    runtime = SkillStateRuntime(client=client, spec=env.spec(), schema_fields=env.schema_fields())
    results = run_episode(env, runtime)
    assert all(result.prompt_tokens > 0 for result in results)
