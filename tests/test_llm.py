from dr.llm import FakeClient, Completion


def test_fake_client_returns_queued_responses_in_order():
    client = FakeClient(responses=["primera", "segunda"])
    assert client.complete(system="s", user="u").text == "primera"
    assert client.complete(system="s", user="u").text == "segunda"


def test_fake_client_records_prompts_it_received():
    client = FakeClient(responses=["x"])
    client.complete(system="spec", user="observacion")
    assert client.calls == [("spec", "observacion")]


def test_fake_client_reports_token_counts():
    client = FakeClient(responses=["hola"])
    completion = client.complete(system="a b c", user="d e")
    assert completion.prompt_tokens == 5
    assert completion.output_tokens == 1


def test_fake_client_raises_when_exhausted():
    client = FakeClient(responses=[])
    try:
        client.complete(system="s", user="u")
    except IndexError:
        return
    raise AssertionError("deberia haber lanzado IndexError")


class _StubMessages:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs

        class _Block:
            type = "text"
            text = "respuesta"

        class _Usage:
            input_tokens = 10
            output_tokens = 2

        class _Response:
            content = [_Block()]
            usage = _Usage()

        return _Response()


class _StubAnthropic:
    def __init__(self, *args, **kwargs) -> None:
        self.messages = _StubMessages()


def _client(monkeypatch, **kwargs):
    """Cliente real con el SDK sustituido: ninguna llamada sale a la API."""
    import dr.llm as llm

    monkeypatch.setattr(llm.anthropic, "Anthropic", _StubAnthropic)
    return llm.AnthropicClient(**kwargs)


def test_haiku_runs_at_temperature_zero(monkeypatch):
    client = _client(monkeypatch, model="claude-haiku-4-5")
    client.complete(system="s", user="u")
    assert client._client.messages.kwargs["temperature"] == 0


def test_reasoning_model_gets_no_temperature_parameter(monkeypatch):
    # SPEC 8: Sonnet 5 corre con su muestreo por defecto; temperatura no esta
    # disponible en modelos de razonamiento.
    client = _client(monkeypatch, model="claude-sonnet-5")
    client.complete(system="s", user="u")
    assert "temperature" not in client._client.messages.kwargs


def test_temperature_can_be_forced_explicitly(monkeypatch):
    client = _client(monkeypatch, model="claude-sonnet-5", temperature=0)
    client.complete(system="s", user="u")
    assert client._client.messages.kwargs["temperature"] == 0
