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


def _tokens_really_spent(client) -> int:
    """Tokens de prompt de TODAS las llamadas, contados como los cuenta FakeClient."""
    return sum(len(system.split()) + len(user.split()) for system, user in client.calls)


def test_runner_counts_the_summary_calls_of_memory():
    from dr.runtimes.memory import MemoryRuntime

    env = Warehouse(horizon=10, seed=2)
    client = FakeClient(responses=["Action: Wait({})"] * 10 + ["resumen"] * 10)
    results = run_episode(env, MemoryRuntime(client=client, spec=env.spec()))
    assert len(client.calls) > 10  # hubo llamadas de resumen
    assert sum(r.prompt_tokens for r in results) == _tokens_really_spent(client)


def test_runner_counts_the_retries_of_skillstate():
    env = Warehouse(horizon=2, seed=2)
    client = FakeClient(
        responses=["patch invalido", _patch_response("Wait({})"), _patch_response("Wait({})")]
    )
    runtime = SkillStateRuntime(client=client, spec=env.spec(), schema_fields=env.schema_fields())
    results = run_episode(env, runtime)
    assert runtime.invalid_patches == 1
    assert len(client.calls) == 3
    assert sum(r.prompt_tokens for r in results) == _tokens_really_spent(client)


def test_unparseable_answers_never_repair_the_world():
    # Inyectar la accion correcta cuando el runtime no produce ninguna deja al
    # brazo que falla en la trayectoria de oro y hace inmedible la sonda C.
    from dr.runtimes.react import ReActRuntime

    env = Warehouse(horizon=6, seed=2)
    client = FakeClient(responses=["no se que hacer"] * 6)
    results = run_episode(env, ReActRuntime(client=client, spec=env.spec()))
    assert len(results) == 6
    assert all(content is None for content in env.shelves.values())


def test_el_resultado_del_paso_arrastra_los_tokens_de_pensamiento():
    # Sin este numero, calibrar el tope de salida es adivinar: el pensamiento se
    # come el presupuesto y la respuesta cortada se lee como fallo del metodo.
    from dr.llm import Completion
    from dr.types import StepResult

    completions = [Completion(text="x", prompt_tokens=1, output_tokens=340,
                              thinking_tokens=300)]
    assert sum(c.thinking_tokens for c in completions) == 300
    assert StepResult(step=0, actionable=True, correct=True, prompt_tokens=1,
                      output_tokens=340, thinking_tokens=300).thinking_tokens == 300
