from dr.envs.base import Environment
from dr.types import Action, Observation


class DummyEnv:
    def __init__(self) -> None:
        self.steps = 0

    def reset(self) -> Observation:
        return Observation(step=0, text="hola", actionable=False)

    def observe(self) -> Observation:
        return Observation(step=self.steps, text="hola", actionable=False)

    def expected_action(self) -> Action:
        return Action(name="Wait")

    def apply(self, action: Action) -> None:
        self.steps += 1

    @property
    def done(self) -> bool:
        return self.steps >= 1

    def spec(self) -> str:
        return "dummy"

    def schema_fields(self) -> list[str]:
        return []


def test_dummy_satisfies_protocol():
    assert isinstance(DummyEnv(), Environment)
