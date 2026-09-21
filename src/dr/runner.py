from __future__ import annotations

import json

from dr.types import Action, StepResult

NO_OP = Action(name="NoOp")


def _anotar(destino, resultado, observation) -> None:
    """Una fila JSON por paso, anexada: una rejilla escribe muchos episodios en el
    mismo fichero y abrirlo en modo escritura dejaria solo el ultimo.

    `http` es 200 porque el cliente solo devuelve una `Completion` despues de una
    respuesta 2xx: si el proveedor fallo, reintento o reviento. Los reintentos
    intermedios no quedan fila a fila -- estan en el log de la corrida."""
    fila = {
        # Esquema del lector de trazas de la casa (`leer-trazas.py`): filtra por
        # `http` y espera `raw` como diccionario. Una lista lo revienta y una fila
        # sin `http` se descarta, asi que la traza se escribe en SU formato -- si no,
        # existe pero nadie la puede abrir, que es lo mismo que no tenerla.
        "http": 200,
        "step": resultado.step,
        "actionable": resultado.actionable,
        "correct": resultado.correct,
        "esperado": resultado.esperado,
        "ejecutado": resultado.ejecutado,
        "raw": {"respuestas": list(resultado.raw)},
        "observation": observation.text,
        "truncated": resultado.truncated,
        # Sin el uso por paso, la densidad de contexto de una celda medida con el
        # adjudicador no existe en ningun sitio, y hubo que citar la de otra condicion.
        "prompt_tokens": resultado.prompt_tokens,
        "output_tokens": resultado.output_tokens,
        "cache_read": resultado.cache_read,
        "thinking_tokens": resultado.thinking_tokens,
        "model_version": resultado.model_version,
    }
    with open(destino, "a", encoding="utf-8") as fichero:
        fichero.write(json.dumps(fila, ensure_ascii=False) + "\n")


def run_episode(env, runtime, traza=None, condiciones=None) -> list[StepResult]:
    """Cruza un entorno con un runtime y devuelve un resultado por paso."""
    env.reset()
    if traza is not None and condiciones:
        # Cabecera con las condiciones de medida. Sin ella, dos ficheros de la misma
        # celda pueden venir de topes de salida distintos y nada lo dice -- que es el
        # error que ya invalido una comparacion entera. Va marcada con `kind` para no
        # romper el conteo de pasos de quien ya lee estos ficheros.
        with open(traza, "a", encoding="utf-8") as fichero:
            fichero.write(json.dumps({"kind": "run_header", "condiciones": condiciones},
                                     ensure_ascii=False) + "\n")
    results: list[StepResult] = []
    while not env.done:
        observation = env.observe()
        expected = env.expected_action()
        action, completions = runtime.act(observation)
        correct = action is not None and action.render() == expected.render()
        resultado = StepResult(
                step=observation.step,
                actionable=observation.actionable,
                correct=correct,
                raw=tuple(c.text for c in completions),
                esperado=expected.render(),
                model_version=next((c.model_version for c in completions
                                    if getattr(c, "model_version", "")), ""),
                ejecutado=action.render() if action is not None else None,
                prompt_tokens=sum(c.prompt_tokens for c in completions),
                output_tokens=sum(c.output_tokens for c in completions),
                state_size=runtime.state_size(),
                truncated=sum(1 for c in completions if c.truncated),
                cache_read=sum(c.cache_read for c in completions),
                cache_write=sum(c.cache_write for c in completions),
                thinking_tokens=sum(
                    getattr(c, "thinking_tokens", 0) for c in completions),
        )
        results.append(resultado)
        if traza is not None:
            _anotar(traza, resultado, observation)
        # Un fallo de parseo es una accion nula, nunca la correcta: inyectar
        # `expected` repararia gratis el mundo del brazo que falla.
        env.apply(action if action is not None else NO_OP)
    return results
