"""Multi-label card roles for outer-loop hand-feature analysis.

Roles are arbitrary strings. A card may hold several at once; hand analysis
counts a card toward every role it carries.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any


CardRoles = dict[int, frozenset[str]]


def normalize_card_roles(raw: Mapping[Any, Any] | None) -> CardRoles:
    """Normalize JSON-friendly role maps to ``dict[int, frozenset[str]]``."""
    if not raw:
        return {}
    result: CardRoles = {}
    for card, roles in raw.items():
        card_id = int(card)
        if roles is None:
            normalized: frozenset[str] = frozenset()
        elif isinstance(roles, str):
            normalized = frozenset({roles})
        else:
            normalized = frozenset(str(role) for role in roles)
        result[card_id] = normalized
    return result


def roles_for(card_roles: CardRoles, card_id: int) -> frozenset[str]:
    """Return all roles assigned to ``card_id`` (empty if unknown)."""
    return card_roles.get(int(card_id), frozenset())


def cards_with_role(card_roles: CardRoles, role: str) -> frozenset[int]:
    """Return card IDs that include ``role``."""
    return frozenset(
        card_id for card_id, roles in card_roles.items() if role in roles
    )


def count_roles(hand: Iterable[int], card_roles: CardRoles) -> dict[str, int]:
    """Count how many hand cards contribute to each role.

    A multi-role card increments every applicable role once per copy in hand.
    """
    counts: Counter[str] = Counter()
    for card in hand:
        counts.update(roles_for(card_roles, int(card)))
    return dict(sorted(counts.items()))


def role_overlaps(hand: Iterable[int], card_roles: CardRoles) -> dict[str, list[str]]:
    """Map each multi-role card present in ``hand`` to its sorted roles."""
    overlaps: dict[str, list[str]] = {}
    for card in hand:
        card_id = int(card)
        roles = roles_for(card_roles, card_id)
        if len(roles) > 1:
            overlaps[str(card_id)] = sorted(roles)
    return overlaps


def hand_features(hand: Iterable[int], card_roles: CardRoles) -> dict[str, Any]:
    """Analytical hand features derived from multi-label card roles."""
    role_counts = count_roles(hand, card_roles)
    return {
        "role_counts": role_counts,
        "roles_present": [role for role, amount in role_counts.items() if amount > 0],
        "role_overlaps": role_overlaps(hand, card_roles),
    }


def role_copies_in_deck(deck: Iterable[int], card_roles: CardRoles, role: str) -> int:
    """How many deck slots satisfy ``role`` (copies count separately)."""
    matching = cards_with_role(card_roles, role)
    return sum(1 for card in deck if int(card) in matching)
