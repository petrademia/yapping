from collections.abc import Callable
from dataclasses import dataclass

from .engine import Decision, Engine


@dataclass(frozen=True)
class SearchResult:
    actions: tuple[int, ...]
    score: float
    decision: Decision
    visited_states: int
    complete: bool = True
    max_depth: int = 0


def search(
    engine: Engine,
    score: Callable[[Decision], float],
    *,
    max_depth: int,
    seed: int = 0,
) -> SearchResult:
    """Exhaustively search deterministic action sequences up to max_depth."""
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")

    frontier = [tuple()]
    seen: set[bytes] = set()
    best: SearchResult | None = None

    while frontier:
        actions = frontier.pop()
        decision = engine.reset(seed)
        for action in actions:
            if action not in decision.legal_actions:
                raise RuntimeError(f"replay produced illegal action {action}")
            decision = engine.step(action)

        key = engine.state_key()
        if key in seen:
            continue
        seen.add(key)

        candidate = SearchResult(actions, float(score(decision)), decision, len(seen), True, max_depth)
        if best is None or candidate.score > best.score:
            best = candidate

        if len(actions) < max_depth and not decision.terminated:
            frontier.extend(actions + (action,) for action in decision.legal_actions)

    assert best is not None
    return SearchResult(best.actions, best.score, best.decision, len(seen), True, max_depth)
