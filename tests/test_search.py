import numpy as np
import pytest

from yapping import Decision, opening_probability, search


class ComboEngine:
    observation_size = 1
    max_actions = 2

    def reset(self, seed=None):
        self.total = 0
        self.depth = 0
        return self._decision()

    def step(self, action):
        self.total += action + 1
        self.depth += 1
        return self._decision()

    def state_key(self):
        return f"{self.depth}:{self.total}".encode()

    def _decision(self):
        done = self.depth == 2
        return Decision(
            np.array([self.total], dtype=np.float32),
            () if done else (0, 1),
            terminated=done,
        )


def test_search_finds_best_combo():
    result = search(
        ComboEngine(),
        lambda decision: float(decision.observation[0]),
        max_depth=2,
        seed=7,
    )
    assert result.actions == (1, 1)
    assert result.score == 4
    assert result.visited_states == 6


def test_opening_probability():
    assert opening_probability(40, 3, 5) == pytest.approx(0.3375506073)
