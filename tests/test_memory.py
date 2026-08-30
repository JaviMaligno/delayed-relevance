from dr.llm import FakeClient
from dr.runtimes.memory import MemoryRuntime
from dr.types import Observation


def _run(runtime, count):
    for step in range(count):
        runtime.act(Observation(step=step, text=f"evento {step}", actionable=False))


def _last_action_prompt(client):
    """Ultimo prompt de decision, ignorando las llamadas de resumen."""
    return [user for system, user in client.calls if "Summarise" not in system][-1]


def test_keeps_only_the_three_most_recent_turns():
    client = FakeClient(responses=["Action: Wait({})"] * 6 + ["resumen"] * 6)
    runtime = MemoryRuntime(client=client, spec="ESPEC")
    _run(runtime, 6)
    user = _last_action_prompt(client)
    assert "evento 5" in user
    assert "evento 1" not in user


def test_older_turns_survive_only_inside_the_summary():
    client = FakeClient(responses=["Action: Wait({})"] * 6 + ["RESUMEN-ACUMULADO"] * 6)
    runtime = MemoryRuntime(client=client, spec="ESPEC")
    _run(runtime, 6)
    user = _last_action_prompt(client)
    assert "RESUMEN-ACUMULADO" in user


def test_summary_is_refreshed_with_a_separate_call():
    client = FakeClient(responses=["Action: Wait({})"] * 5 + ["resumen"] * 5)
    runtime = MemoryRuntime(client=client, spec="ESPEC")
    _run(runtime, 5)
    summarising_calls = [call for call in client.calls if "Summarise" in call[0]]
    assert len(summarising_calls) >= 1


def test_no_prompt_mentions_a_domain_the_runtime_should_not_know():
    # El runtime no sabe nada del dominio (contrato de runtimes/base.py): el dominio
    # solo puede entrar por `spec` o por la observacion, nunca por texto del runtime.
    client = FakeClient(responses=["Action: Wait({})"] * 6 + ["resumen"] * 6)
    runtime = MemoryRuntime(client=client, spec="ESPEC")
    _run(runtime, 6)
    for system, user in client.calls:
        assert "warehouse" not in (system + user).lower()
