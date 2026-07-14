import numpy as np
import pytest

from yapping import (
    Decision,
    expected_choice,
    minimax_replay,
    opening_probability,
    robust_choice,
    search,
)


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


def test_hidden_interruption_choices_do_not_leak_information():
    payoffs = {
        "greedy_line": {"ash": 2, "impermanence": 9},
        "safe_line": {"ash": 6, "impermanence": 6},
    }
    assert robust_choice(payoffs).choice == "safe_line"
    choice, score = expected_choice(payoffs, {"ash": 0.2, "impermanence": 0.8})
    assert choice == "greedy_line"
    assert score == pytest.approx(7.6)


def test_minimax_replay_chooses_strongest_worst_case():
    payoffs = {(0, 0): 3, (0, 1): 5, (1, 0): 2, (1, 1): 8}
    result = minimax_replay(
        lambda path: path,
        lambda path: () if len(path) == 2 else (0, 1),
        lambda path: payoffs[path],
        lambda path: len(path) == 2,
        lambda path: len(path) % 2,
        max_depth=2,
        max_nodes=20,
    )
    assert result.actions == (0, 0)
    assert result.score == 3
    assert result.complete
