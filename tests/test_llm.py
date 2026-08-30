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


def test_no_model_ever_receives_a_temperature_parameter(monkeypatch):
    # El SDK anthropic 1.x elimino `temperature` de Messages.create(): no esta
    # disponible para ningun modelo. La reproducibilidad es estadistica (spec 8).
    for model in ("claude-haiku-4-5", "claude-sonnet-5"):
        client = _client(monkeypatch, model=model)
        client.complete(system="s", user="u")
        assert "temperature" not in client._client.messages.kwargs


def test_sdk_create_signature_has_no_temperature():
    # Test de regresion contra el entorno: si una version futura del SDK
    # reintrodujera temperature, esta decision hay que revisarla a conciencia.
    import inspect

    import anthropic

    parameters = inspect.signature(anthropic.Anthropic.__init__).parameters
    assert "api_key" in parameters
    create = anthropic.resources.messages.Messages.create
    assert "temperature" not in inspect.signature(create).parameters
