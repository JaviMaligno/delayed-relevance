"""El mismo Gemini, servido por Vertex AI y pagado.

Existe por una razon de medicion, no de comodidad: la clave de AI Studio es de
cuenta gratuita y su cupo corta la rejilla a medias, asi que R1 -- cinco horizontes
por cinco seeds por cuatro runtimes -- no cabe ahi. Vertex sirve el mismo
`gemini-3-flash-preview` en el proyecto de pago, y el token sale de `gcloud`, igual
que el de Foundry sale de `az login`: ningun secreto en disco.

Lo que estos tests protegen es que el cambio de backend **no cambie lo que ve el
modelo**. Si el cuerpo enviado difiere del de AI Studio, la corrida deja de ser
comparable con la de humo y con la Tabla 1 del paper.
"""
import pytest

from dr.llm import GeminiClient, build_client

PROYECTO = "proyecto-de-prueba"


@pytest.fixture
def vertex(monkeypatch):
    """POST, token y proyecto sustituidos: ni red ni gcloud."""
    import dr.llm as llm

    estado = {"enviado": None, "url": None, "cabeceras": None, "tokens": [],
              "respuesta": {
                  "candidates": [{"content": {"parts": [{"text": "ok"}]},
                                  "finishReason": "STOP"}],
                  "usageMetadata": {"promptTokenCount": 10,
                                    "candidatesTokenCount": 2},
                  "modelVersion": "gemini-3-flash-preview"}}

    def _fake_post(url, headers, payload):
        estado["url"] = url
        estado["cabeceras"] = headers
        estado["enviado"] = payload
        return estado["respuesta"]

    def _fake_token():
        estado["tokens"].append(f"token-{len(estado['tokens'])}")
        return estado["tokens"][-1]

    monkeypatch.setattr(llm, "post_json", _fake_post)
    monkeypatch.setattr(llm, "gcloud_access_token", _fake_token)
    monkeypatch.setenv("GEMINI_VERTEX_PROJECT", PROYECTO)
    # El entorno real de quien corre los tests suele traer estas puestas, y un test
    # que dependa de ellas pasa aqui y falla en CI (o al reves).
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GEMINI_VERTEX_LOCATION", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return estado


def _cliente(**kwargs):
    return GeminiClient(model="gemini-3-flash-preview", backend="vertex", **kwargs)


def test_vertex_no_necesita_clave_de_api(vertex):
    # La clave gratuita es justo lo que este backend viene a no usar.
    _cliente().complete(system="s", user="u")
    assert "x-goog-api-key" not in vertex["cabeceras"]


def test_la_peticion_va_al_endpoint_de_vertex_en_global(vertex):
    # Gemini 3 no se sirve en us-central1: `locations/global` no es un detalle, es la
    # unica localizacion donde el modelo de su Tabla 1 responde.
    _cliente().complete(system="s", user="u")
    assert vertex["url"] == (
        "https://aiplatform.googleapis.com/v1beta1/projects/proyecto-de-prueba"
        "/locations/global/publishers/google/models/"
        "gemini-3-flash-preview:generateContent")


def test_una_localizacion_regional_usa_su_propio_host(vertex, monkeypatch):
    monkeypatch.setenv("GEMINI_VERTEX_LOCATION", "us-central1")
    _cliente().complete(system="s", user="u")
    assert vertex["url"].startswith(
        "https://us-central1-aiplatform.googleapis.com/v1beta1/")
    assert "/locations/us-central1/" in vertex["url"]


def test_el_token_viaja_en_authorization_y_no_en_la_url(vertex):
    _cliente().complete(system="s", user="u")
    assert vertex["cabeceras"]["Authorization"] == "Bearer token-0"
    assert "token-0" not in vertex["url"]


def test_el_proyecto_de_cuota_viaja_en_su_cabecera(vertex):
    # Con credenciales de usuario (ADC de `gcloud auth login`) Vertex responde 403
    # sin esta cabecera. El sintoma es "falta cuota", que se lee como limite de plan.
    _cliente().complete(system="s", user="u")
    assert vertex["cabeceras"]["x-goog-user-project"] == PROYECTO


def test_el_cuerpo_es_el_mismo_que_contra_ai_studio(vertex):
    # La comparabilidad del experimento depende de esto: mismo greedy, mismo system,
    # mismo orden de partes. Si el backend cambia el prompt, mide otra cosa.
    _cliente().complete(system="spec", user="ultima", cache_prefix=["uno ", "dos "])
    cuerpo = vertex["enviado"]
    assert cuerpo["systemInstruction"]["parts"][0]["text"] == "spec"
    assert cuerpo["generationConfig"]["temperature"] == 0.0
    assert cuerpo["generationConfig"]["topP"] == 1.0
    partes = cuerpo["contents"][0]["parts"]
    assert "".join(p["text"] for p in partes) == "uno dos ultima"


def test_el_presupuesto_de_pensamiento_tambien_viaja_en_vertex(vertex):
    _cliente(thinking_budget=0).complete(system="s", user="u")
    assert vertex["enviado"]["generationConfig"]["thinkingConfig"] == {
        "thinkingBudget": 0}


def test_el_token_se_reutiliza_mientras_no_caduque(vertex):
    # Un `gcloud auth print-access-token` por episodio anade medio segundo a cada
    # llamada de una rejilla de miles.
    cliente = _cliente()
    cliente.complete(system="s", user="u")
    cliente.complete(system="s", user="u")
    assert vertex["tokens"] == ["token-0"]


def test_el_token_se_refresca_cuando_se_acerca_su_caducidad(vertex, monkeypatch):
    # Los tokens de gcloud viven una hora y R1 dura mas. Sin refresco, la rejilla se
    # cae a mitad con un 401 y lo pagado se pierde si el checkpoint no lo salva.
    import dr.llm as llm

    reloj = {"t": 1000.0}
    monkeypatch.setattr(llm.time, "monotonic", lambda: reloj["t"])
    cliente = _cliente()
    cliente.complete(system="s", user="u")
    reloj["t"] += llm.VERTEX_TOKEN_TTL + 1
    cliente.complete(system="s", user="u")
    assert vertex["tokens"] == ["token-0", "token-1"]


def test_sin_proyecto_falla_al_construir(vertex, monkeypatch):
    # Antes del primer episodio, no dos minutos despues con un 404 de publisher.
    monkeypatch.delenv("GEMINI_VERTEX_PROJECT", raising=False)
    monkeypatch.setattr("dr.llm.gcloud_project", lambda: "")
    with pytest.raises(RuntimeError):
        _cliente()


def test_el_proyecto_sale_de_gcloud_si_no_hay_variable(vertex, monkeypatch):
    monkeypatch.delenv("GEMINI_VERTEX_PROJECT", raising=False)
    monkeypatch.setattr("dr.llm.gcloud_project", lambda: "proyecto-del-cli")
    _cliente().complete(system="s", user="u")
    assert "/projects/proyecto-del-cli/" in vertex["url"]


def test_el_proveedor_se_declara_vertex(vertex):
    # El nombre del proveedor entra en el nombre del checkpoint. Si Vertex se
    # declarase "gemini", sus episodios se mezclarian con los de la clave gratuita en
    # el mismo fichero y la procedencia de cada celda se perderia.
    assert _cliente().provider == "vertex"


def test_la_fabrica_enruta_a_vertex_con_el_proveedor_forzado(vertex):
    cliente = build_client("gemini-3-flash-preview", provider="vertex")
    assert isinstance(cliente, GeminiClient)
    assert cliente.provider == "vertex"


def test_la_fabrica_pasa_el_presupuesto_de_pensamiento_a_vertex(vertex):
    assert build_client("gemini-3-flash-preview", provider="vertex",
                        thinking_budget=0).thinking_budget == 0
