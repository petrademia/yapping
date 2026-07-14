import numpy as np
import pytest
from types import SimpleNamespace

from yapping import (
    Decision,
    expected_choice,
    hidden_minimax_replay,
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


def test_minimax_replay_reuses_exact_transposition():
    def replay(path):
        depth = len(path)
        key = (b"root" if depth == 0 else b"middle" if depth == 1 else b"terminal")
        return SimpleNamespace(key=key, depth=depth)

    result = minimax_replay(
        replay,
        lambda node: () if node.depth == 2 else (0, 1),
        lambda _node: 5.0,
        lambda node: node.depth == 2,
        lambda node: node.depth % 2,
        max_depth=2,
        max_nodes=20,
    )
    assert result.actions == (0, 0)
    assert result.visited_states == 4
    assert result.complete


def test_hidden_minimax_keeps_worlds_together_after_pass():
    # Ash may pass and remain hidden, or activate and reveal its world.
    payoffs = {
        ("ash", "greedy", "pass"): 9, ("ash", "greedy", "hit"): 1,
        ("no_ash", "greedy", "pass"): 9,
        ("ash", "safe", "pass"): 5, ("ash", "safe", "hit"): 5,
        ("no_ash", "safe", "pass"): 5,
    }
    result = hidden_minimax_replay(
        lambda scenario, path: (scenario, path),
        lambda state: (() if len(state[1]) == 2 else
                       ((0, 1) if not state[1] or state[0] == "ash" else (0,))),
        lambda state, index: (("greedy", "safe")[index] if not state[1] else
                              (("pass", "hit")[index] if state[0] == "ash" else "pass")),
        lambda state: payoffs[(state[0], ("greedy", "safe")[state[1][0]],
                               (("pass", "hit")[state[1][1]] if state[0] == "ash" else "pass"))],
        lambda state: len(state[1]) == 2,
        lambda state: 0 if not state[1] else 1,
        ("ash", "no_ash"),
        max_depth=2,
        max_nodes=20,
    )
    assert result.action == "safe"
    assert result.score == 5
