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


class _ClienteQueAnotaTopes(FakeClient):
    def __init__(self, responses):
        super().__init__(responses=responses)
        self.topes = []

    def complete(self, system, user, max_tokens=None, cache_prefix=None):
        if "Summarise" in system:
            self.topes.append(max_tokens)
        return super().complete(system, user, max_tokens, cache_prefix)


def test_el_tope_del_resumen_se_puede_subir_sin_tocar_el_de_serie():
    # Haiku desborda el tope de 1.200 en la mitad de los resumenes de T=200 y Gemini
    # nunca. Para saber si la columna de Memory mide el resumen o el corte, hace falta
    # medir con otro tope sin mover el que ya fija todo lo medido.
    de_serie = _ClienteQueAnotaTopes(["Action: Wait({})"] * 5 + ["r"] * 5)
    _run(MemoryRuntime(client=de_serie, spec="E"), 5)
    subido = _ClienteQueAnotaTopes(["Action: Wait({})"] * 5 + ["r"] * 5)
    _run(MemoryRuntime(client=subido, spec="E", summary_max_tokens=2400), 5)
    assert de_serie.topes and set(de_serie.topes) == {1200}
    assert subido.topes and set(subido.topes) == {2400}
