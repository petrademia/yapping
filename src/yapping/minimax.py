from collections.abc import Callable, Mapping, Sequence
from itertools import product
from dataclasses import dataclass
from typing import Any


class BoundCache:
    """Alpha-beta transposition cache shared by the replay-based minimax variants.

    Entries store a bound label ("exact", "lower", "upper") alongside the
    score and payload, so a cutoff in one branch can narrow the window for a
    later visit to the same key instead of re-searching it.
    """

    def __init__(self):
        self._entries = {}

    def probe(self, key, alpha, beta):
        """Return (score, payload, complete, exact) if resolved, else None.

        Also returns the (possibly narrowed) alpha/beta window.
        """
        entry = self._entries.get(key)
        if entry is None:
            return None, alpha, beta
        score, payload, bound = entry
        if bound == "exact":
            return (score, payload, True, True), alpha, beta
        if bound == "lower":
            alpha = max(alpha, score)
        else:
            beta = min(beta, score)
        if beta <= alpha:
            return (score, payload, True, False), alpha, beta
        return None, alpha, beta

    def store_cutoff(self, key, score, payload, bound, complete):
        """Store a beta-cutoff bound ("lower" or "upper") if the branch was complete."""
        if complete:
            self._entries[key] = (score, payload, bound)

    def store_final(self, key, alpha_in, beta_in, score, payload, complete):
        """Store the fully-searched result and return whether it is exact."""
        if not complete:
            return False
        bound = ("upper" if score <= alpha_in else
                 "lower" if score >= beta_in else "exact")
        self._entries[key] = (score, payload, bound)
        return bound == "exact"

    def mark_exact(self, key, score, payload):
        self._entries[key] = (score, payload, "exact")


@dataclass(frozen=True)
class MinimaxResult:
    actions: tuple[int, ...]
    score: float
    visited_states: int
    complete: bool
    max_depth: int = 0
    max_nodes: int = 0
    action_values: Mapping[int, float] = ()


@dataclass(frozen=True)
class HiddenMinimaxResult:
    """Maximin result where player 0 cannot inspect the hidden scenario."""

    action: object | None
    score: float
    scenario_scores: Mapping[str, float]
    visited_states: int
    complete: bool
    max_depth: int = 0
    max_nodes: int = 0


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
    cache = BoundCache()
    root_action_values = {}

    def visit(path, depth, alpha, beta):
        nonlocal visited
        node = replay(path)
        cache_key = (getattr(node, "key", repr(node)), depth)
        alpha_in, beta_in = alpha, beta
        hit, alpha, beta = cache.probe(cache_key, alpha, beta)
        if hit is not None:
            return hit
        visited += 1
        actions = tuple(legal_actions(node))
        is_terminal = terminal(node)
        if is_terminal or depth == max_depth or not actions or visited >= max_nodes:
            score = float(evaluate(node))
            if is_terminal:
                cache.mark_exact(cache_key, score, tuple())
            return score, tuple(), is_terminal, is_terminal

        maximize = owner(node) == 0
        best_score = float("-inf") if maximize else float("inf")
        best_path = tuple()
        complete = True
        for action in actions:
            score, suffix, child_complete, _ = visit(
                path + (action,), depth + 1, alpha, beta
            )
            if depth == 0:
                root_action_values[action] = score
            complete &= child_complete
            if (maximize and score > best_score) or (not maximize and score < best_score):
                best_score, best_path = score, (action,) + suffix
            if maximize:
                alpha = max(alpha, best_score)
            else:
                beta = min(beta, best_score)
            if beta <= alpha:
                cache.store_cutoff(cache_key, best_score, best_path,
                                    "lower" if maximize else "upper", complete)
                return best_score, best_path, complete, False
            if visited >= max_nodes:
                complete = False
                break
        exact = cache.store_final(cache_key, alpha_in, beta_in, best_score, best_path, complete)
        return best_score, best_path, complete, complete and exact

    score, actions, complete, _ = visit(tuple(), 0, float("-inf"), float("inf"))
    return MinimaxResult(actions, score, visited, complete, max_depth, max_nodes,
                         root_action_values)


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
    cache = BoundCache()

    def visit(paths, depth, alpha, beta):
        nonlocal visited
        nodes = {scenario: replay(scenario, path) for scenario, path in paths.items()}
        cache_key = tuple(sorted(
            (scenario, getattr(node, "key", repr(node))) for scenario, node in nodes.items()
        ))
        alpha_in, beta_in = alpha, beta
        hit, alpha, beta = cache.probe(cache_key, alpha, beta)
        if hit is not None:
            return hit
        world_cost = len(nodes)
        if visited + world_cost > max_nodes:
            visited = max_nodes
            value = min(float(evaluate(node)) for node in nodes.values())
            return value, None, False, False
        visited += world_cost
        is_terminal = all(terminal(node) for node in nodes.values())
        if depth >= max_depth or visited >= max_nodes or is_terminal:
            value = min(float(evaluate(node)) for node in nodes.values())
            if is_terminal:
                cache.mark_exact(cache_key, value, None)
            return value, None, is_terminal and visited < max_nodes, is_terminal

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
            best, best_key, complete = float("-inf"), None, True
            for key in common:
                child_paths = {scenario: paths[scenario] + (keyed[key][scenario],)
                               for scenario in nodes}
                value, _, child_complete, _ = visit(child_paths, depth + 1, alpha, beta)
                complete &= child_complete
                if value > best:
                    best, best_key = value, key
                alpha = max(alpha, best)
                if beta <= alpha:
                    cache.store_cutoff(cache_key, best, best_key, "lower", complete)
                    return best, best_key, complete, False
            exact = cache.store_final(cache_key, alpha_in, beta_in, best, best_key, complete)
            return best, best_key, complete, complete and exact

        choices = [
            [(scenario, index, action_key(node, index)) for index in legal_actions(node)]
            for scenario, node in nodes.items()
        ]
        best, complete = float("inf"), True
        for policy in product(*choices):
            groups = {}
            for scenario, index, key in policy:
                groups.setdefault(key, {})[scenario] = paths[scenario] + (index,)
            value = float("inf")
            for group in groups.values():
                child, _, child_complete, _ = visit(group, depth + 1, alpha, beta)
                complete &= child_complete
                value = min(value, child)
                if value <= alpha:
                    break
            best = min(best, value)
            beta = min(beta, best)
            if beta <= alpha:
                cache.store_cutoff(cache_key, best, None, "upper", complete)
                return best, None, complete, False
        if complete:
            cache.store_final(cache_key, alpha_in, beta_in, best, None, complete)
        exact = cache.store_final(cache_key, alpha_in, beta_in, best, None, complete)
        return best, None, complete, complete and exact

    value, action, complete, _ = visit(
        {scenario: tuple() for scenario in scenarios}, 0, float("-inf"), float("inf")
    )
    return HiddenMinimaxResult(action, value, {}, visited, complete, max_depth, max_nodes)
