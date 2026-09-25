"""El adaptador de Gemini, sin tocar la red.

Gemini entra por una razon concreta: es el modelo de su Tabla 1 y admite
`temperature=0`. Con decodificacion greedy las seeds vuelven a ser instancias del
entorno en vez de tiradas del muestreo, que es la limitacion mas seria del bloque 1.
Si estos tests dejan de comprobar que el greedy sale en la peticion, esa propiedad se
pierde sin que nadie lo note.
"""
import pytest

from dr.llm import Completion, GeminiClient, build_client


def _respuesta(text="respuesta", finish="STOP", usage=None, thought=None):
    parts = [{"text": text}]
    if thought is not None:
        parts.insert(0, {"text": thought, "thought": True})
    return {
        "candidates": [{"content": {"parts": parts}, "finishReason": finish}],
        "usageMetadata": usage or {"promptTokenCount": 10, "candidatesTokenCount": 2},
        "modelVersion": "gemini-3-flash-preview-09-2026",
    }


@pytest.fixture
def capturado(monkeypatch):
    """Sustituye el POST por uno que guarda lo enviado y devuelve lo que se le diga."""
    import dr.llm as llm

    estado = {"enviado": None, "url": None, "cabeceras": None,
              "respuesta": _respuesta()}

    def _fake_post(url, headers, payload):
        estado["url"] = url
        estado["cabeceras"] = headers
        estado["enviado"] = payload
        return estado["respuesta"]

    monkeypatch.setattr(llm, "post_json", _fake_post)
    monkeypatch.setenv("GEMINI_API_KEY", "ficticia")
    return estado


def test_la_peticion_va_en_greedy(capturado):
    GeminiClient(model="gemini-3-flash-preview").complete(system="s", user="u")
    config = capturado["enviado"]["generationConfig"]
    assert config["temperature"] == 0.0
    assert config["topP"] == 1.0


def test_el_tope_de_salida_viaja_en_la_peticion(capturado):
    GeminiClient(model="gemini-3-flash-preview", max_tokens=600).complete(
        system="s", user="u")
    assert capturado["enviado"]["generationConfig"]["maxOutputTokens"] == 600


def test_el_tope_por_llamada_manda_sobre_el_del_cliente(capturado):
    GeminiClient(model="gemini-3-flash-preview", max_tokens=600).complete(
        system="s", user="u", max_tokens=1200)
    assert capturado["enviado"]["generationConfig"]["maxOutputTokens"] == 1200


def test_el_sistema_va_como_system_instruction(capturado):
    GeminiClient(model="gemini-3-flash-preview").complete(system="spec", user="obs")
    assert capturado["enviado"]["systemInstruction"]["parts"][0]["text"] == "spec"


def test_el_prefijo_troceado_llega_entero_y_en_orden(capturado):
    # En Anthropic los bloques existen para marcar el corte de cache. Aqui no hay
    # corte que marcar todavia, pero el modelo tiene que ver exactamente el mismo
    # texto que veria alli: si el prompt difiere, la comparacion entre proveedores
    # deja de medir el modelo.
    GeminiClient(model="gemini-3-flash-preview").complete(
        system="s", user="ultima", cache_prefix=["uno ", "dos "])
    partes = capturado["enviado"]["contents"][0]["parts"]
    assert "".join(p["text"] for p in partes) == "uno dos ultima"


def test_la_clave_viaja_en_cabecera_y_no_en_la_url(capturado):
    # La URL acaba en logs y en mensajes de error; la cabecera no.
    GeminiClient(model="gemini-3-flash-preview").complete(system="s", user="u")
    assert "ficticia" not in capturado["url"]
    assert capturado["cabeceras"]["x-goog-api-key"] == "ficticia"


def test_sin_clave_falla_al_construir(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        GeminiClient(model="gemini-3-flash-preview")


def test_el_uso_se_lee_de_usage_metadata(capturado):
    capturado["respuesta"] = _respuesta(usage={
        "promptTokenCount": 1500,
        "candidatesTokenCount": 120,
        "cachedContentTokenCount": 900,
    })
    salida = GeminiClient(model="gemini-3-flash-preview").complete(system="s", user="u")
    # `promptTokenCount` incluye los cacheados: la entrada no cacheada es 1500 - 900.
    # Este test esperaba antes 1500, que es justo la doble cuenta que encontro la
    # revision adversarial 8.
    assert salida.prompt_tokens == 600
    assert salida.output_tokens == 120
    assert salida.cache_read == 900


def test_los_tokens_de_pensamiento_cuentan_como_salida_y_se_guardan_aparte(capturado):
    # Se facturan como salida. Sumarlos evita subestimar el coste; guardarlos aparte
    # evita que un modelo que piensa mucho parezca uno que escribe mucho.
    capturado["respuesta"] = _respuesta(usage={
        "promptTokenCount": 10,
        "candidatesTokenCount": 40,
        "thoughtsTokenCount": 300,
    })
    salida = GeminiClient(model="gemini-3-flash-preview").complete(system="s", user="u")
    assert salida.output_tokens == 340
    assert salida.thinking_tokens == 300


def test_el_texto_de_pensamiento_no_entra_en_la_respuesta(capturado):
    capturado["respuesta"] = _respuesta(text="Action: Wait", thought="dejame pensar")
    salida = GeminiClient(model="gemini-3-flash-preview").complete(system="s", user="u")
    assert salida.text == "Action: Wait"


def test_un_final_que_no_es_stop_marca_truncado(capturado):
    # El artefacto numero 8 del proyecto fue justo esto sin contar: una respuesta
    # cortada parte el bloque JSON del parche y el fallo se lee como del metodo.
    capturado["respuesta"] = _respuesta(finish="MAX_TOKENS")
    salida = GeminiClient(model="gemini-3-flash-preview").complete(system="s", user="u")
    assert salida.truncated is True


def test_un_final_stop_no_marca_truncado(capturado):
    assert GeminiClient(model="gemini-3-flash-preview").complete(
        system="s", user="u").truncated is False


def test_se_registra_la_version_de_modelo_que_contesta(capturado):
    # El ID pedido es un preview: el que conteste puede no ser el de su Tabla 1, y
    # eso hay que poder declararlo con el dato delante.
    salida = GeminiClient(model="gemini-3-flash-preview").complete(system="s", user="u")
    assert salida.model_version == "gemini-3-flash-preview-09-2026"


def test_una_respuesta_sin_candidatos_no_revienta_el_episodio(capturado):
    # Un bloqueo por filtros devuelve 200 sin candidates. Debe leerse como una
    # respuesta vacia y truncada, no como una excepcion a mitad de rejilla.
    capturado["respuesta"] = {"usageMetadata": {"promptTokenCount": 5},
                              "promptFeedback": {"blockReason": "SAFETY"}}
    salida = GeminiClient(model="gemini-3-flash-preview").complete(system="s", user="u")
    assert salida.text == ""
    assert salida.truncated is True


def test_la_fabrica_enruta_por_el_nombre_del_modelo(capturado):
    from dr.llm import AnthropicClient

    assert isinstance(build_client("gemini-3-flash-preview"), GeminiClient)
    assert build_client("claude-haiku-4-5", provider="api").__class__ is AnthropicClient


def test_la_fabrica_respeta_el_proveedor_forzado(capturado):
    assert isinstance(build_client("lo-que-sea", provider="gemini"), GeminiClient)


def test_completion_sigue_construyendose_sin_los_campos_nuevos():
    # Los corredores existentes crean Completion con los campos de antes.
    salida = Completion(text="x", prompt_tokens=1, output_tokens=1)
    assert salida.thinking_tokens == 0
    assert salida.model_version == ""


def test_un_prompt_que_no_cabe_se_reconoce_en_los_dos_proveedores():
    from dr.llm import es_desbordamiento_de_contexto as desborda

    assert desborda(Exception("prompt is too long: 210000 tokens > 200000"))
    assert desborda(RuntimeError('HTTP 400 de Gemini: {"error": {"message": '
                                 '"The input token count exceeds the maximum"}}'))
    # Un 400 por otra cosa NO es desbordamiento: tiene que reventar la corrida, no
    # contarse como una celda no medible.
    assert not desborda(RuntimeError('HTTP 400 de Gemini: invalid generationConfig'))
    assert not desborda(RuntimeError("HTTP 403 de Gemini: permiso denegado"))


def test_el_presupuesto_de_pensamiento_viaja_en_la_peticion(capturado):
    # Apagarlo es una decision que hay que poder tomar con datos: el pensamiento
    # cuenta contra el tope de salida, y en la corrida de humo dos respuestas de
    # diez salieron truncadas con el tope calibrado sobre Claude.
    GeminiClient(model="gemini-3-flash-preview", thinking_budget=0).complete(
        system="s", user="u")
    config = capturado["enviado"]["generationConfig"]
    assert config["thinkingConfig"] == {"thinkingBudget": 0}


def test_sin_presupuesto_declarado_no_se_manda_thinking_config(capturado):
    GeminiClient(model="gemini-3-flash-preview").complete(system="s", user="u")
    assert "thinkingConfig" not in capturado["enviado"]["generationConfig"]


def test_la_fabrica_pasa_el_presupuesto_de_pensamiento(capturado):
    cliente = build_client("gemini-3-flash-preview", thinking_budget=0)
    assert cliente.thinking_budget == 0
