"""Conditioned hand-utility aggregation for outer-loop consistency reports.

Given analyzed opening-hand rows (each with hypergeometric ``probability`` and
solver ``score`` / category breakdowns), summarize expected utility under role
composition predicates.

Sampling caveat: ``analyze_consistency`` evaluates a set of unique sampled
hands. Bucket ``probability_mass`` is the sum of those hands' hypergeometric
weights, not a claim that the sample covers the full deck distribution.
``weighted_*`` fields renormalize within a bucket's evaluated mass.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any


SCORE_CATEGORIES = (
    "board_value",
    "interaction_value",
    "follow_up_value",
    "survival_value",
)

# Default role count buckets: (label, kind, threshold)
# kind is "eq" or "ge".
DEFAULT_ROLE_BUCKETS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "starter": (("=0", "eq", 0), (">=1", "ge", 1)),
    "extender": (("=0", "eq", 0), ("=1", "eq", 1), ("=2", "eq", 2), (">=3", "ge", 3)),
    "interaction": (("=0", "eq", 0), ("=1", "eq", 1), ("=2", "eq", 2), (">=3", "ge", 3)),
    "brick": (("=0", "eq", 0), ("=1", "eq", 1), (">=2", "ge", 2)),
    "recovery": (("=0", "eq", 0), ("=1", "eq", 1), (">=2", "ge", 2)),
}

# Joint predicates: label -> sequence of (role, kind, threshold)
DEFAULT_JOINT_CONDITIONS: tuple[tuple[str, tuple[tuple[str, str, int], ...]], ...] = (
    ("starter>=1,extender=0", (("starter", "ge", 1), ("extender", "eq", 0))),
    ("starter>=1,extender=1", (("starter", "ge", 1), ("extender", "eq", 1))),
    ("starter>=1,extender=2", (("starter", "ge", 1), ("extender", "eq", 2))),
    ("starter>=1,extender>=3", (("starter", "ge", 1), ("extender", "ge", 3))),
)


def role_count(row: Mapping[str, Any], role: str) -> int:
    """Role count from a consistency row's classification (0 if absent)."""
    classification = row.get("classification") or {}
    key = f"{role}_count"
    if key in classification:
        return int(classification[key])
    counts = classification.get("role_counts") or {}
    return int(counts.get(role, 0))


def count_matches(count: int, kind: str, threshold: int) -> bool:
    if kind == "eq":
        return count == threshold
    if kind == "ge":
        return count >= threshold
    raise ValueError(f"unknown bucket kind: {kind}")


def predicate_from_clauses(
    clauses: Sequence[tuple[str, str, int]],
) -> Callable[[Mapping[str, Any]], bool]:
    """Build a row predicate from ``(role, kind, threshold)`` clauses (AND)."""

    def predicate(row: Mapping[str, Any]) -> bool:
        return all(
            count_matches(role_count(row, role), kind, threshold)
            for role, kind, threshold in clauses
        )

    return predicate


def sampling_context(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Describe how evaluated-hand probability mass should be interpreted."""
    mass = sum(float(row.get("probability", 0.0)) for row in rows)
    return {
        "mode": "unique_hands_sample",
        "evaluated_hands": len(rows),
        "raw_probability_mass": mass,
        "covers_full_deck_distribution": False,
        "note": (
            "Bucket probability_mass sums hypergeometric P(h) over evaluated "
            "unique hands only. It is not a full-deck fraction. weighted_* "
            "fields are conditional means renormalized within each bucket's "
            "evaluated mass."
        ),
    }


def empty_bucket_summary() -> dict[str, Any]:
    return {
        "hands": 0,
        "probability_mass": 0.0,
        "mass_share_of_evaluated": 0.0,
        "weighted_score": None,
        "weighted_categories": None,
        "complete_fraction": None,
        "provisional_hands": 0,
        "weighted_score_loss": None,
        "weighted_category_loss": None,
    }


def summarize_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    evaluated_mass: float | None = None,
) -> dict[str, Any]:
    """Probability-weighted summary for a set of consistency rows.

    ``probability_mass`` is the raw sum of hypergeometric weights.
    ``weighted_*`` renormalize by that mass among the provided rows.
    ``mass_share_of_evaluated`` divides by the parent evaluated mass when given.
    """
    if not rows:
        summary = empty_bucket_summary()
        if evaluated_mass is not None:
            summary["mass_share_of_evaluated"] = 0.0
        return summary

    mass = sum(float(row["probability"]) for row in rows)
    if mass <= 0:
        summary = empty_bucket_summary()
        summary["hands"] = len(rows)
        return summary

    parent = evaluated_mass if evaluated_mass is not None else mass
    categories = {
        category: sum(
            float(row["categories"][category]) * float(row["probability"])
            for row in rows
        )
        / mass
        for category in SCORE_CATEGORIES
    }
    summary: dict[str, Any] = {
        "hands": len(rows),
        "probability_mass": mass,
        "mass_share_of_evaluated": (mass / parent) if parent else 0.0,
        "weighted_score": sum(
            float(row["score"]) * float(row["probability"]) for row in rows
        )
        / mass,
        "weighted_categories": categories,
        "complete_fraction": sum(bool(row["complete"]) for row in rows) / len(rows),
        "provisional_hands": sum(not row["complete"] for row in rows),
        "weighted_score_loss": None,
        "weighted_category_loss": None,
    }

    paired = [row for row in rows if "score_loss" in row]
    if paired:
        paired_mass = sum(float(row["probability"]) for row in paired)
        if paired_mass > 0:
            summary["paired_hands"] = len(paired)
            summary["paired_probability_mass"] = paired_mass
            summary["weighted_score_loss"] = sum(
                float(row["score_loss"]) * float(row["probability"]) for row in paired
            ) / paired_mass
            summary["weighted_category_loss"] = {
                category: sum(
                    float(row["category_deltas"][category]) * float(row["probability"])
                    for row in paired
                )
                / paired_mass
                for category in SCORE_CATEGORIES
                if all(category in row.get("category_deltas", {}) for row in paired)
            }
    return summary


def summarize_by_predicate(
    rows: Sequence[Mapping[str, Any]],
    predicate: Callable[[Mapping[str, Any]], bool],
    *,
    evaluated_mass: float | None = None,
) -> dict[str, Any]:
    matched = [row for row in rows if predicate(row)]
    parent = (
        evaluated_mass
        if evaluated_mass is not None
        else sum(float(row.get("probability", 0.0)) for row in rows)
    )
    return summarize_rows(matched, evaluated_mass=parent)


def summarize_role_counts(
    rows: Sequence[Mapping[str, Any]],
    role: str,
    buckets: Sequence[tuple[str, str, int]] | None = None,
) -> dict[str, Any]:
    """Bucket rows by a single role count and summarize each bucket."""
    specs = tuple(buckets) if buckets is not None else DEFAULT_ROLE_BUCKETS.get(
        role, (("=0", "eq", 0), ("=1", "eq", 1), ("=2", "eq", 2), (">=3", "ge", 3))
    )
    evaluated_mass = sum(float(row.get("probability", 0.0)) for row in rows)
    result: dict[str, Any] = {}
    for label, kind, threshold in specs:
        result[label] = summarize_by_predicate(
            rows,
            lambda row, kind=kind, threshold=threshold: count_matches(
                role_count(row, role), kind, threshold
            ),
            evaluated_mass=evaluated_mass,
        )
    return result


def summarize_joint_conditions(
    rows: Sequence[Mapping[str, Any]],
    conditions: Sequence[tuple[str, Sequence[tuple[str, str, int]]]] | None = None,
) -> dict[str, Any]:
    """Summarize named AND-clauses over role counts (starter/extender by default)."""
    specs = tuple(conditions) if conditions is not None else DEFAULT_JOINT_CONDITIONS
    evaluated_mass = sum(float(row.get("probability", 0.0)) for row in rows)
    return {
        label: summarize_by_predicate(
            rows, predicate_from_clauses(clauses), evaluated_mass=evaluated_mass
        )
        for label, clauses in specs
    }


def conditioned_hand_utility(
    rows: Sequence[Mapping[str, Any]],
    *,
    roles: Iterable[str] | None = None,
    role_buckets: Mapping[str, Sequence[tuple[str, str, int]]] | None = None,
    joint_conditions: Sequence[tuple[str, Sequence[tuple[str, str, int]]]] | None = None,
) -> dict[str, Any]:
    """Full conditioned report for one interruption's analyzed hands."""
    role_list = list(roles) if roles is not None else list(DEFAULT_ROLE_BUCKETS)
    bucket_map = role_buckets or DEFAULT_ROLE_BUCKETS
    by_role = {
        role: summarize_role_counts(rows, role, bucket_map.get(role))
        for role in role_list
    }
    return {
        "sampling": sampling_context(rows),
        "by_role": by_role,
        "joint": summarize_joint_conditions(rows, joint_conditions),
    }


def role_density_opening_profile(
    deck: Sequence[int],
    card_roles: Mapping[int, frozenset[str]],
    roles: Iterable[str] | None = None,
    hand_size: int = 5,
) -> dict[str, Any]:
    """Phase 3D primitive: theoretical opening count probs from role density.

    Does not change the deck or run the solver; pairs deck role-copy counts
    with hypergeometric opening probabilities for interpretation alongside
    conditioned utility buckets.
    """
    from .probability import opening_at_least_probability, opening_count_probability
    from .roles import role_copies_in_deck

    role_list = list(roles) if roles is not None else list(DEFAULT_ROLE_BUCKETS)
    deck_size = len(deck)
    profile: dict[str, Any] = {}
    for role in role_list:
        copies = role_copies_in_deck(deck, dict(card_roles), role)
        exact = {
            str(count): opening_count_probability(deck_size, copies, hand_size, count)
            for count in range(0, min(hand_size, copies) + 1)
        }
        profile[role] = {
            "role_copies_in_deck": copies,
            "hand_size": hand_size,
            "opening_count_probability": exact,
            "opening_at_least_probability": {
                str(minimum): opening_at_least_probability(
                    deck_size, copies, hand_size, minimum
                )
                for minimum in range(0, min(hand_size, copies) + 1)
            },
        }
    return profile
