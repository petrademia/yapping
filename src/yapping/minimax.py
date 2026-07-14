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

    def visit(paths, depth):
        nonlocal visited
        nodes = {scenario: replay(scenario, path) for scenario, path in paths.items()}
        cache_key = tuple(sorted(
            (scenario, getattr(node, "key", repr(node))) for scenario, node in nodes.items()
        ))
        if cache_key in cache:
            return cache[cache_key]
        visited += len(nodes)
        complete = visited < max_nodes
        if (depth >= max_depth or not complete
                or all(terminal(node) for node in nodes.values())):
            result = ({scenario: float(evaluate(node)) for scenario, node in nodes.items()},
                      None, all(terminal(node) for node in nodes.values()) and complete)
            cache[cache_key] = result
            return result

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
                result = ({scenario: float(evaluate(node)) for scenario, node in nodes.items()},
                          None, False)
                cache[cache_key] = result
                return result
            candidates = []
            for key in common:
                child_paths = {scenario: paths[scenario] + (keyed[key][scenario],)
                               for scenario in nodes}
                scores, _, child_complete = visit(child_paths, depth + 1)
                candidates.append((min(scores.values()), key, scores, child_complete))
            score, key, scores, child_complete = max(candidates, key=lambda item: item[0])
            result = scores, key, complete and all(item[3] for item in candidates)
            cache[cache_key] = result
            return result

        choices = [
            [(scenario, index, action_key(node, index)) for index in legal_actions(node)]
            for scenario, node in nodes.items()
        ]
        candidates = []
        for policy in product(*choices):
            groups = {}
            for scenario, index, key in policy:
                groups.setdefault(key, {})[scenario] = paths[scenario] + (index,)
            scores, policy_complete = {}, complete
            for group in groups.values():
                child_scores, _, child_complete = visit(group, depth + 1)
                scores.update(child_scores)
                policy_complete &= child_complete
            candidates.append((min(scores.values()), scores, policy_complete))
        _, scores, child_complete = min(candidates, key=lambda item: item[0])
        result = scores, None, complete and all(item[2] for item in candidates)
        cache[cache_key] = result
        return result

    paths = {scenario: tuple() for scenario in scenarios}
    scores, action, complete = visit(paths, 0)
    return HiddenMinimaxResult(action, min(scores.values()), scores, visited, complete)
