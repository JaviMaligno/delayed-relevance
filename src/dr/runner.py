from __future__ import annotations

from dr.types import Action, StepResult

NO_OP = Action(name="NoOp")


def run_episode(env, runtime) -> list[StepResult]:
    """Cruza un entorno con un runtime y devuelve un resultado por paso."""
    env.reset()
    results: list[StepResult] = []
    while not env.done:
        observation = env.observe()
        expected = env.expected_action()
        action, completions = runtime.act(observation)
        correct = action is not None and action.render() == expected.render()
        results.append(
            StepResult(
                step=observation.step,
                actionable=observation.actionable,
                correct=correct,
                prompt_tokens=sum(c.prompt_tokens for c in completions),
                output_tokens=sum(c.output_tokens for c in completions),
                state_size=runtime.state_size(),
                truncated=sum(1 for c in completions if c.truncated),
                cache_read=sum(c.cache_read for c in completions),
                cache_write=sum(c.cache_write for c in completions),
                thinking_tokens=sum(
                    getattr(c, "thinking_tokens", 0) for c in completions),
            )
        )
        # Un fallo de parseo es una accion nula, nunca la correcta: inyectar
        # `expected` repararia gratis el mundo del brazo que falla.
        env.apply(action if action is not None else NO_OP)
    return results
