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
