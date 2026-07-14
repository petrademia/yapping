import numpy as np
import pytest

from yapping import Decision, YgoEnv


class ScriptedEngine:
    observation_size = 2
    max_actions = 3

    def reset(self, seed=None):
        return Decision(np.array([0, seed or 0], dtype=np.float32), (0, 2))

    def step(self, action):
        return Decision(
            np.array([1, action], dtype=np.float32),
            (),
            reward=1.0,
            terminated=True,
            winner=0,
        )

    def state_key(self):
        return b"terminal"


def test_environment_contract():
    env = YgoEnv(ScriptedEngine())
    observation, _ = env.reset(seed=7)
    assert observation["action_mask"].tolist() == [1, 0, 1]

    observation, reward, terminated, truncated, info = env.step(2)
    assert reward == 1.0
    assert terminated and not truncated
    assert info["winner"] == 0
    assert observation["action_mask"].tolist() == [0, 0, 0]


def test_illegal_action_is_rejected():
    env = YgoEnv(ScriptedEngine())
    env.reset()
    with pytest.raises(ValueError, match="illegal action 1"):
        env.step(1)
