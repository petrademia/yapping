from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MinimaxResult:
    actions: tuple[int, ...]
    score: float
    visited_states: int
    complete: bool


def minimax_replay(
    replay: Callable[[tuple[int, ...]], Any],
    legal_actions: Callable[[Any], Sequence[int]],
    evaluate: Callable[[Any], float],
    terminal: Callable[[Any], bool],
    owner: Callable[[Any], int],
    *,
    max_depth: int,
    max_nodes: int,
) -> MinimaxResult:
    """Alpha-beta minimax for deterministic engines reconstructed by replay."""
    visited = 0

    def visit(path, depth, alpha, beta):
        nonlocal visited
        node = replay(path)
        visited += 1
        actions = tuple(legal_actions(node))
        is_terminal = terminal(node)
        if is_terminal or depth == max_depth or not actions or visited >= max_nodes:
            return float(evaluate(node)), tuple(), is_terminal

        maximize = owner(node) == 0
        best_score = float("-inf") if maximize else float("inf")
        best_path = tuple()
        complete = True
        for action in actions:
            score, suffix, child_complete = visit(path + (action,), depth + 1, alpha, beta)
            complete &= child_complete
            if (maximize and score > best_score) or (not maximize and score < best_score):
                best_score, best_path = score, (action,) + suffix
            if maximize:
                alpha = max(alpha, best_score)
            else:
                beta = min(beta, best_score)
            if beta <= alpha:
                break
            if visited >= max_nodes:
                complete = False
                break
        return best_score, best_path, complete

    score, actions, complete = visit(tuple(), 0, float("-inf"), float("inf"))
    return MinimaxResult(actions, score, visited, complete)
