"""Opening-hand sampling helpers and deck/hand coherence checks."""

from __future__ import annotations

import hashlib
import json
import random
from typing import Iterable, Sequence


def hand_id(hand: Sequence[int]) -> str:
    """Stable id for a multiset opening hand (order-independent)."""
    normalized = sorted(int(card) for card in hand)
    payload = json.dumps(normalized, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def trajectory_id(
    hand_key: str,
    scenario_id: str,
    *,
    max_nodes: int,
    max_depth: int,
) -> str:
    """Stable id for one complete search over (hand, scenario, limits)."""
    payload = f"{hand_key}|{scenario_id}|{max_nodes}|{max_depth}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def validate_hand_in_deck(deck: Sequence[int], hand: Sequence[int]) -> None:
    """Raise if ``hand`` is not a 5-card multiset subset of ``deck``."""
    if len(hand) != 5:
        raise ValueError("opening_hand must contain exactly five cards")
    remaining = list(deck)
    for card in hand:
        try:
            remaining.remove(int(card))
        except ValueError as error:
            raise ValueError(f"opening hand card {card} is not in this deck") from error


def sample_unique_hands(
    deck: Sequence[int],
    amount: int,
    seed: int,
) -> Iterable[tuple[int, ...]]:
    """Yield ``amount`` unique sorted 5-card hands from ``deck``."""
    pool = list(deck)
    if len(pool) < 5:
        raise ValueError("deck must contain at least five cards")
    rng = random.Random(seed)
    seen: set[tuple[int, ...]] = set()
    while len(seen) < amount:
        hand = tuple(sorted(rng.sample(pool, 5)))
        if hand not in seen:
            seen.add(hand)
            yield hand
