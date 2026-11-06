"""Parseo de los clientes por suscripcion con salidas reales recortadas, sin llamar al CLI."""
import json

import pytest

import dr.llm as llm
from dr.llm import ClaudeCliClient, CodexCliClient, ErrorDeCli, SinLogin, build_client

# Salida real de `claude -p --output-format json` (5-nov-2026), recortada.
CLAUDE_OK = {
    "type": "result", "subtype": "success", "is_error": False,
    "stop_reason": "end_turn", "total_cost_usd": 0.0002327,
    "result": 'Razono.\nAction: Wait({})',
    "usage": {"input_tokens": 2, "cache_creation_input_tokens": 785,
              "cache_read_input_tokens": 120, "output_tokens": 151,
              "output_tokens_details": {"thinking_tokens": 141}},
    "modelUsage": {"claude-haiku-5-5": {"canonicalModel": "claude-haiku-5-5",
                                        "costUSD": 0.0002327}},
}

# Lo que devuelve al pasar CLAUDE_CODE_MAX_OUTPUT_TOKENS (medido con 100).
CLAUDE_TOPE = {
    "type": "result", "subtype": "success", "is_error": True, "stop_reason": "stop_sequence",
    "result": "API Error: Claude's response exceeded the 100 output token maximum. To "
              "configure this behavior, set the CLAUDE_CODE_MAX_OUTPUT_TOKENS environment "
              "variable.",
    "usage": {"input_tokens": 3, "output_tokens": 400},
    "modelUsage": {"claude-haiku-5-5": {"canonicalModel": "claude-haiku-5-5"}},
}

# Salida real de `codex exec --json` (5-nov-2026).
CODEX_OK = [
    '{"type":"thread.started","thread_id":"01a1ab9c-9084-7fc3-a2c3-aa1306f4cc8d"}',
    '{"type":"turn.started"}',
    '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"OK-42"}}',
    '{"type":"turn.completed","usage":{"input_tokens":21040,"cached_input_tokens":13824,'
    '"cache_write_input_tokens":0,"output_tokens":7,"reasoning_output_tokens":3}}',
]


def test_claude_lee_uso_cache_coste_y_modelo():
    c = ClaudeCliClient._leer(CLAUDE_OK)
    assert c.text.endswith("Action: Wait({})")
    assert (c.prompt_tokens, c.cache_write, c.cache_read) == (2, 785, 120)
    assert (c.output_tokens, c.thinking_tokens) == (151, 141)
    assert c.model_version == "claude-haiku-5-5"
    assert c.cost_usd == pytest.approx(0.0002327)
    assert not c.truncated


def test_claude_stop_reason_max_tokens_es_truncada():
    c = ClaudeCliClient._leer({**CLAUDE_OK, "stop_reason": "max_tokens"})
    assert c.truncated


def test_claude_tope_de_salida_es_respuesta_truncada_y_vacia():
    c = ClaudeCliClient._leer(CLAUDE_TOPE)
    assert c.truncated and c.text == ""


def test_claude_otro_error_se_reintenta():
    with pytest.raises(ErrorDeCli):
        ClaudeCliClient._leer({**CLAUDE_OK, "is_error": True, "result": "API Error: 529 overloaded"})


def test_claude_sin_login_no_se_reintenta():
    with pytest.raises(SinLogin):
        ClaudeCliClient._leer_salida(1, "Not logged in · Please run /login", "")
    with pytest.raises(SinLogin):
        ClaudeCliClient._leer_salida(
            1, json.dumps({**CLAUDE_OK, "is_error": True,
                           "result": "Invalid API key · Please run /login"}), "")


def test_claude_salida_sin_json_es_transitoria():
    with pytest.raises(ErrorDeCli):
        ClaudeCliClient._leer_salida(1, "", "boom")


def test_claude_prompt_por_stdin_y_system_en_fichero(monkeypatch):
    vistos = {}

    def falso(argumentos, entrada, timeout, cwd=None, env=None):
        fichero = argumentos[argumentos.index("--system-prompt-file") + 1]
        with open(fichero, encoding="utf-8") as fh:
            vistos["system"] = fh.read()
        vistos.update(argumentos=argumentos, entrada=entrada, env=env)
        return 0, json.dumps(CLAUDE_OK), ""

    monkeypatch.setattr(llm, "ejecutar_cli", falso)
    cliente = ClaudeCliClient(max_tokens=8192)
    c = cliente.complete("SYS\nlinea 2", "user", max_tokens=1200, cache_prefix=["a\n", "b\n"])
    assert vistos["system"] == "SYS\nlinea 2"
    assert vistos["entrada"] == "a\nb\nuser"
    assert "--bare" not in vistos["argumentos"]
    assert vistos["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "1200"
    assert c.segundos >= 0


def test_claude_reintenta_un_fallo_transitorio(monkeypatch):
    salidas = iter([(1, "", "socket hang up"), (0, json.dumps(CLAUDE_OK), "")])
    monkeypatch.setattr(llm, "ejecutar_cli", lambda *a, **k: next(salidas))
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    assert ClaudeCliClient().complete("s", "u").cache_write == 785


def test_codex_guarda_el_resumen_de_razonamiento_y_lo_pide():
    lineas = CODEX_OK[:2] + [
        '{"type":"item.completed","item":{"id":"item_0","type":"reasoning",'
        '"text":"**Doubting the notice**"}}',
        '{"type":"item.completed","item":{"id":"item_1","type":"reasoning",'
        '"text":"**Keeping shelf occupied**"}}',
    ] + CODEX_OK[2:]
    c = CodexCliClient._leer(lineas, "m")
    assert c.text == "OK-42"
    assert c.razonamiento == "**Doubting the notice**\n**Keeping shelf occupied**"
    assert CodexCliClient._leer(CODEX_OK, "m").razonamiento == ""
    a = CodexCliClient()._argumentos()
    assert "model_reasoning_summary=detailed" in a
    assert not any("reasoning_summary" in x
                   for x in CodexCliClient(resumen_razonamiento=None)._argumentos())


def test_codex_lee_mensaje_y_normaliza_la_cache():
    c = CodexCliClient._leer(CODEX_OK, "gpt-6.1-sol")
    assert c.text == "OK-42"
    assert c.prompt_tokens == 21040 - 13824
    assert c.cache_read == 13824
    assert (c.output_tokens, c.thinking_tokens) == (7, 3)
    assert c.model_version == "pedido:gpt-6.1-sol"


def test_codex_sin_turno_completo_es_error():
    with pytest.raises(ErrorDeCli):
        CodexCliClient._leer(CODEX_OK[:2] + ['{"type":"turn.failed","error":{"message":"x"}}'],
                             "m", 1)


def test_codex_sin_login():
    with pytest.raises(SinLogin):
        CodexCliClient._leer([], "m", 1, "Error: Not logged in. Run `codex login`.")


def test_codex_compone_system_y_user_por_stdin(monkeypatch):
    vistos = {}

    def falso(argumentos, entrada, timeout, cwd=None, env=None):
        vistos.update(argumentos=argumentos, entrada=entrada, cwd=cwd)
        return 0, "\n".join(CODEX_OK), ""

    monkeypatch.setattr(llm, "ejecutar_cli", falso)
    CodexCliClient().complete("SPEC", "EVENTO", cache_prefix="HIST\n")
    e = vistos["entrada"]
    assert e.index("BEGIN SYSTEM") < e.index("SPEC") < e.index("END SYSTEM") \
        < e.index("BEGIN USER") < e.index("HIST\nEVENTO") < e.index("END USER")
    a = vistos["argumentos"]
    assert a[-1] == "-" and "--ignore-user-config" in a and "--json" in a
    assert a[a.index("-s") + 1] == "read-only"


def test_el_subproceso_no_hereda_claves_de_api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-no")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "r")
    monkeypatch.setenv("CLAUDE_CODE_USE_FOUNDRY", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-no")
    monkeypatch.setenv("CODEX_HOME", "C:/codex")
    vistos = {}

    def falso(argumentos, entrada, timeout, cwd=None, env=None):
        vistos.setdefault("envs", []).append(env)
        return 0, (json.dumps(CLAUDE_OK) if "-p" in argumentos else "\n".join(CODEX_OK)), ""

    monkeypatch.setattr(llm, "ejecutar_cli", falso)
    ClaudeCliClient().complete("s", "u")
    CodexCliClient().complete("s", "u")
    for env in vistos["envs"]:
        assert not any(k.upper().startswith(("ANTHROPIC_", "OPENAI_", "CLAUDE_CODE_USE"))
                       for k in env)
    assert vistos["envs"][1]["CODEX_HOME"] == "C:/codex"


def test_build_client_enruta_los_cli():
    assert build_client("claude-haiku-5-5", "claude-cli").provider == "claude-cli"
    assert build_client("gpt-6.1-sol", "codex-cli").provider == "codex-cli"
