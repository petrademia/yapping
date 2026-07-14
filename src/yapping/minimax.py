from collections.abc import Callable, Mapping, Sequence
from itertools import product
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MinimaxResult:
    actions: tuple[int, ...]
    score: float
    visited_states: int
    complete: bool


@dataclass(frozen=True)
class HiddenMinimaxResult:
    """Maximin result where player 0 cannot inspect the hidden scenario."""

    action: object | None
    score: float
    scenario_scores: Mapping[str, float]
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
    cache = {}

    def visit(path, depth, alpha, beta):
        nonlocal visited
        node = replay(path)
        cache_key = (getattr(node, "key", repr(node)), depth)
        if cache_key in cache:
            score, actions = cache[cache_key]
            return score, actions, True, True
        visited += 1
        actions = tuple(legal_actions(node))
        is_terminal = terminal(node)
        if is_terminal or depth == max_depth or not actions or visited >= max_nodes:
            return float(evaluate(node)), tuple(), is_terminal, is_terminal

        maximize = owner(node) == 0
        best_score = float("-inf") if maximize else float("inf")
        best_path = tuple()
        complete = True
        exact = True
        for action in actions:
            score, suffix, child_complete, child_exact = visit(
                path + (action,), depth + 1, alpha, beta
            )
            complete &= child_complete
            exact &= child_exact
            if (maximize and score > best_score) or (not maximize and score < best_score):
                best_score, best_path = score, (action,) + suffix
            if maximize:
                alpha = max(alpha, best_score)
            else:
                beta = min(beta, best_score)
            if beta <= alpha:
                return best_score, best_path, complete, False
            if visited >= max_nodes:
                complete = False
                break
        if exact:
            cache[cache_key] = best_score, best_path
        return best_score, best_path, complete, exact

    score, actions, complete, _ = visit(tuple(), 0, float("-inf"), float("inf"))
    return MinimaxResult(actions, score, visited, complete)


def hidden_minimax_replay(
    replay: Callable[[str, tuple[int, ...]], Any],
    legal_actions: Callable[[Any], Sequence[int]],
    action_key: Callable[[Any, int], object],
    evaluate: Callable[[Any], float],
    terminal: Callable[[Any], bool],
    owner: Callable[[Any], int],
    scenarios: Sequence[str],
    *,
    max_depth: int,
    max_nodes: int,
) -> HiddenMinimaxResult:
    """Replay maximin with shared player-0 choices until play reveals a world.

    Opponent actions are grouped by their public action key. A pass therefore
    keeps worlds such as ``ash`` and ``no_ash`` together; activating Ash splits
    the belief state because the player observes it.
    """
    visited = 0
    cache = {}

    def visit(paths, depth, alpha, beta):
        nonlocal visited
        nodes = {scenario: replay(scenario, path) for scenario, path in paths.items()}
        cache_key = tuple(sorted(
            (scenario, getattr(node, "key", repr(node))) for scenario, node in nodes.items()
        ))
        if cache_key in cache:
            value, action = cache[cache_key]
            return value, action, True, True
        visited += len(nodes)
        is_terminal = all(terminal(node) for node in nodes.values())
        if depth >= max_depth or visited >= max_nodes or is_terminal:
            return (min(float(evaluate(node)) for node in nodes.values()), None,
                    is_terminal and visited < max_nodes, is_terminal)

        node_owner = {owner(node) for node in nodes.values()}
        if len(node_owner) != 1:
            raise ValueError("hidden worlds reached different decision owners")
        if node_owner.pop() == 0:
            keyed = {}
            for scenario, node in nodes.items():
                for index in legal_actions(node):
                    keyed.setdefault(action_key(node, index), {})[scenario] = index
            common = [key for key, indices in keyed.items() if len(indices) == len(nodes)]
            if not common:
                return min(float(evaluate(node)) for node in nodes.values()), None, False, False
            best, best_key, complete, exact = float("-inf"), None, True, True
            for key in common:
                child_paths = {scenario: paths[scenario] + (keyed[key][scenario],)
                               for scenario in nodes}
                value, _, child_complete, child_exact = visit(child_paths, depth + 1, alpha, beta)
                complete &= child_complete
                exact &= child_exact
                if value > best:
                    best, best_key = value, key
                alpha = max(alpha, best)
                if beta <= alpha:
                    return best, best_key, complete, False
            if exact:
                cache[cache_key] = best, best_key
            return best, best_key, complete, exact

        choices = [
            [(scenario, index, action_key(node, index)) for index in legal_actions(node)]
            for scenario, node in nodes.items()
        ]
        best, complete, exact = float("inf"), True, True
        for policy in product(*choices):
            groups = {}
            for scenario, index, key in policy:
                groups.setdefault(key, {})[scenario] = paths[scenario] + (index,)
            value = float("inf")
            for group in groups.values():
                child, _, child_complete, child_exact = visit(group, depth + 1, alpha, beta)
                complete &= child_complete
                exact &= child_exact
                value = min(value, child)
                if value <= alpha:
                    break
            best = min(best, value)
            beta = min(beta, best)
            if beta <= alpha:
                return best, None, complete, False
        if exact:
            cache[cache_key] = best, None
        return best, None, complete, exact

    value, action, complete, _ = visit(
        {scenario: tuple() for scenario in scenarios}, 0, float("-inf"), float("inf")
    )
    return HiddenMinimaxResult(action, value, {}, visited, complete)
