import gymnasium as gym
import numpy as np

from .engine import Decision, Engine


class YgoEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, engine: Engine):
        self.engine = engine
        self.action_space = gym.spaces.Discrete(engine.max_actions)
        self.observation_space = gym.spaces.Dict(
            {
                "state": gym.spaces.Box(
                    low=-np.inf,
                    high=np.inf,
                    shape=(engine.observation_size,),
                    dtype=np.float32,
                ),
                "action_mask": gym.spaces.MultiBinary(engine.max_actions),
            }
        )
        self._decision: Decision | None = None

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._decision = self.engine.reset(seed)
        return self._encode(self._decision), self._info(self._decision)

    def step(self, action):
        if self._decision is None:
            raise RuntimeError("reset() must be called before step()")
        action = int(action)
        if action not in self._decision.legal_actions:
            raise ValueError(f"illegal action {action}")
        self._decision = self.engine.step(action)
        return (
            self._encode(self._decision),
            self._decision.reward,
            self._decision.terminated,
            False,
            self._info(self._decision),
        )

    def _encode(self, decision):
        mask = np.zeros(self.engine.max_actions, dtype=np.int8)
        mask[list(decision.legal_actions)] = 1
        return {"state": decision.observation, "action_mask": mask}

    @staticmethod
    def _info(decision):
        return {"winner": decision.winner}
