from __future__ import annotations

from dr.types import StepResult


def run_episode(env, runtime) -> list[StepResult]:
    """Cruza un entorno con un runtime y devuelve un resultado por paso."""
    env.reset()
    results: list[StepResult] = []
    while not env.done:
        observation = env.observe()
        expected = env.expected_action()
        action, completion = runtime.act(observation)
        correct = action is not None and action.render() == expected.render()
        results.append(
            StepResult(
                step=observation.step,
                actionable=observation.actionable,
                correct=correct,
                prompt_tokens=completion.prompt_tokens if completion else 0,
                output_tokens=completion.output_tokens if completion else 0,
                state_size=runtime.state_size(),
            )
        )
        env.apply(action if action is not None else expected)
    return results
