"""Outer-loop consistency analytics: hand features vs solver outcomes.

Terminology principle
---------------------
Every analytical term maps to an observable quantity, explicit mathematical
function, or configurable predicate.

Layers (kept distinct):

* **Card semantics / roles** – descriptive hypotheses (``starter``, …).
* **Hand features** – counts/overlaps derived from roles.
* **Solver outcomes** – ``U(H, I)`` and category breakdowns from search.
* **Derived metrics** – ceiling, interruption loss, floor, threshold rates.
* **Deck distributions** – probability-weighted aggregates over hands.

Roles are **not** playability. Playability is a threshold on solver utility:

    Playable_T(H, I) := U(H, I) >= T

with ``T`` explicit and configurable.

Sampling caveat
---------------
``analyze_consistency`` evaluates unique sampled hands.
``evaluated_probability_mass`` is the sum of those hands' hypergeometric
weights and is typically << 1. Normalized rates are among evaluated mass
only unless full-deck coverage is separately established.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


SCORE_CATEGORIES = (
    "board_value",
    "interaction_value",
    "follow_up_value",
    "survival_value",
)

DEFAULT_SUCCESS_THRESHOLDS: tuple[float, ...] = (5.0, 10.0, 15.0)

# Default role count buckets: (label, kind, threshold); kind is "eq" or "ge".
DEFAULT_ROLE_BUCKETS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "starter": (("=0", "eq", 0), (">=1", "ge", 1)),
    "extender": (("=0", "eq", 0), ("=1", "eq", 1), ("=2", "eq", 2), (">=3", "ge", 3)),
    "interaction": (("=0", "eq", 0), ("=1", "eq", 1), ("=2", "eq", 2), (">=3", "ge", 3)),
    "brick": (("=0", "eq", 0), ("=1", "eq", 1), (">=2", "ge", 2)),
    "recovery": (("=0", "eq", 0), ("=1", "eq", 1), (">=2", "ge", 2)),
}

DEFAULT_JOINT_CONDITIONS: tuple[tuple[str, tuple[tuple[str, str, int], ...]], ...] = (
    ("starter>=1,extender=0", (("starter", "ge", 1), ("extender", "eq", 0))),
    ("starter>=1,extender=1", (("starter", "ge", 1), ("extender", "eq", 1))),
    ("starter>=1,extender=2", (("starter", "ge", 1), ("extender", "eq", 2))),
    ("starter>=1,extender>=3", (("starter", "ge", 1), ("extender", "ge", 3))),
)

JOINT_DELTA_ORDER: tuple[str, ...] = (
    "starter>=1,extender=0",
    "starter>=1,extender=1",
    "starter>=1,extender=2",
    "starter>=1,extender>=3",
)


@dataclass(frozen=True)
class HandCondition:
    """Predicate on a hand-feature role count.

    ``operator`` is ``">="`` / ``"ge"`` or ``"="`` / ``"eq"``.
    This is a hand-feature filter, not a claim about playability.
    """

    role: str
    operator: str
    value: int

    def matches(self, row: Mapping[str, Any]) -> bool:
        kind = _operator_kind(self.operator)
        return count_matches(role_count(row, self.role), kind, self.value)

    def as_clause(self) -> tuple[str, str, int]:
        return self.role, _operator_kind(self.operator), int(self.value)

    def label(self) -> str:
        op = ">=" if _operator_kind(self.operator) == "ge" else "="
        return f"{self.role}{op}{self.value}"


def _operator_kind(operator: str) -> str:
    if operator in (">=", "ge"):
        return "ge"
    if operator in ("=", "==", "eq"):
        return "eq"
    raise ValueError(f"unknown operator: {operator}")


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


def predicate_from_conditions(
    conditions: Sequence[HandCondition],
) -> Callable[[Mapping[str, Any]], bool]:
    """AND-compose ``HandCondition`` predicates."""
    return predicate_from_clauses([condition.as_clause() for condition in conditions])


def sampling_context(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Describe how evaluated-hand probability mass should be interpreted."""
    mass = sum(float(row.get("probability", 0.0)) for row in rows)
    return {
        "mode": "unique_hands_sample",
        "evaluated_hands": len(rows),
        "evaluated_probability_mass": mass,
        "raw_probability_mass": mass,  # alias kept for earlier callers
        "covers_full_deck_distribution": False,
        "note": (
            "evaluated_probability_mass sums hypergeometric P(h) over evaluated "
            "unique hands only. It is not a full-deck fraction. "
            "normalized_weighted_score / evaluated_sample_* rates renormalize "
            "within evaluated mass. Do not read those rates as exact deck-wide "
            "percentages unless coverage is independently complete."
        ),
    }


def empty_bucket_summary() -> dict[str, Any]:
    return {
        "hands": 0,
        "evaluated_hands": 0,
        "probability_mass": 0.0,
        "mass_share_of_evaluated": 0.0,
        "weighted_score": None,
        "normalized_weighted_score": None,
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
    ``normalized_weighted_score`` (alias ``weighted_score``) renormalizes by
    that mass among the provided rows.
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
        summary["evaluated_hands"] = len(rows)
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
    weighted_score = sum(
        float(row["score"]) * float(row["probability"]) for row in rows
    ) / mass
    summary: dict[str, Any] = {
        "hands": len(rows),
        "evaluated_hands": len(rows),
        "probability_mass": mass,
        "mass_share_of_evaluated": (mass / parent) if parent else 0.0,
        "weighted_score": weighted_score,
        "normalized_weighted_score": weighted_score,
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


def conditional_bucket_deltas(
    bucket_summaries: Mapping[str, Mapping[str, Any]],
    ordered_labels: Sequence[str],
) -> dict[str, Any]:
    """Observational differences between adjacent conditioned buckets.

    ``E[U|B_{k}] - E[U|B_{k-1}]`` is a **conditional association**, not a
    counterfactual card contribution (see extender replacement analysis).
    """
    deltas: dict[str, Any] = {}
    for previous, current in zip(ordered_labels, ordered_labels[1:]):
        left = bucket_summaries.get(previous) or {}
        right = bucket_summaries.get(current) or {}
        left_score = left.get("normalized_weighted_score", left.get("weighted_score"))
        right_score = right.get("normalized_weighted_score", right.get("weighted_score"))
        key = f"{current}_minus_{previous}"
        if left_score is None or right_score is None:
            deltas[key] = {
                "from": previous,
                "to": current,
                "normalized_weighted_score_delta": None,
                "kind": "conditional_association",
                "note": (
                    "Missing bucket mean; observational delta undefined. "
                    "Not a counterfactual card replacement."
                ),
            }
            continue
        deltas[key] = {
            "from": previous,
            "to": current,
            "normalized_weighted_score_delta": float(right_score) - float(left_score),
            "kind": "conditional_association",
            "note": (
                "Observational difference between hand-feature buckets. "
                "Not a causal/counterfactual card contribution."
            ),
        }
    return deltas


def weighted_quantile(
    rows: Sequence[Mapping[str, Any]],
    quantile: float,
    *,
    score_key: str = "score",
) -> float | None:
    """Probability-weighted quantile of ``score_key`` (inclusive CDF).

    Rows are sorted by score ascending. Returns the first score where the
    cumulative probability mass reaches ``quantile * total_mass``.
    """
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be in [0, 1]")
    if not rows:
        return None
    ordered = sorted(
        ((float(row[score_key]), float(row["probability"])) for row in rows),
        key=lambda item: item[0],
    )
    total = sum(weight for _, weight in ordered)
    if total <= 0:
        return None
    if quantile == 0.0:
        return ordered[0][0]
    target = quantile * total
    cumulative = 0.0
    for score, weight in ordered:
        cumulative += weight
        if cumulative + 1e-15 >= target:
            return score
    return ordered[-1][0]


def utility_distribution(
    rows: Sequence[Mapping[str, Any]],
    thresholds: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Probability-weighted utility distribution among evaluated hands.

    Threshold rates use:

        Playable_T := U >= T

    with ``T`` visible in the output. ``evaluated_sample_success_rate`` is
    normalized within evaluated mass, not claimed as a full-deck rate.
    """
    thresholds = tuple(DEFAULT_SUCCESS_THRESHOLDS if thresholds is None else thresholds)
    mass = sum(float(row.get("probability", 0.0)) for row in rows)
    if not rows or mass <= 0:
        return {
            "evaluated_probability_mass": mass,
            "covers_full_deck_distribution": False,
            "weighted_mean": None,
            "weighted_median": None,
            "weighted_p10": None,
            "weighted_p25": None,
            "weighted_p75": None,
            "weighted_p90": None,
            "thresholds": {
                _threshold_key(threshold): {
                    "threshold": float(threshold),
                    "predicate": f"U >= {float(threshold)}",
                    "probability_mass": 0.0,
                    "evaluated_sample_success_rate": None,
                }
                for threshold in thresholds
            },
        }

    weighted_mean = sum(
        float(row["score"]) * float(row["probability"]) for row in rows
    ) / mass
    threshold_block: dict[str, Any] = {}
    for threshold in thresholds:
        t = float(threshold)
        success_mass = sum(
            float(row["probability"])
            for row in rows
            if float(row["score"]) >= t
        )
        threshold_block[_threshold_key(t)] = {
            "threshold": t,
            "predicate": f"U >= {t}",
            "probability_mass": success_mass,
            "evaluated_sample_success_rate": success_mass / mass,
        }
    return {
        "evaluated_probability_mass": mass,
        "covers_full_deck_distribution": False,
        "weighted_mean": weighted_mean,
        "weighted_median": weighted_quantile(rows, 0.5),
        "weighted_p10": weighted_quantile(rows, 0.10),
        "weighted_p25": weighted_quantile(rows, 0.25),
        "weighted_p75": weighted_quantile(rows, 0.75),
        "weighted_p90": weighted_quantile(rows, 0.90),
        "thresholds": threshold_block,
    }


def _threshold_key(threshold: float) -> str:
    if float(threshold).is_integer():
        return str(int(threshold))
    return str(threshold)


def ceiling(score_by_interruption: Mapping[str, float], *, baseline: str = "none") -> float:
    """Ceiling(H) = U(H, no_interruption) for the configured baseline name."""
    return float(score_by_interruption[baseline])


def interruption_loss(
    score_by_interruption: Mapping[str, float],
    interruption: str,
    *,
    baseline: str = "none",
) -> float:
    """Loss(H, I) = Ceiling(H) - U(H, I). Compatible with row ``score_loss``."""
    return ceiling(score_by_interruption, baseline=baseline) - float(
        score_by_interruption[interruption]
    )


def floor_over_configured(
    score_by_interruption: Mapping[str, float],
) -> float:
    """Floor(H) = min_i U(H, i) over the configured/evaluated interruption set."""
    if not score_by_interruption:
        raise ValueError("score_by_interruption must be non-empty")
    return min(float(score) for score in score_by_interruption.values())


def expected_utility(
    score_by_interruption: Mapping[str, float],
    interruption_weights: Mapping[str, float],
) -> float:
    """ExpectedUtility(H) = Σ P(i) U(H, i) when scenario weights are explicit.

    Raises if any scored interruption lacks a weight. Does not invent equal
    probabilities.
    """
    missing = [name for name in score_by_interruption if name not in interruption_weights]
    if missing:
        raise ValueError(
            "interruption weights missing for: " + ", ".join(sorted(missing))
        )
    return sum(
        float(interruption_weights[name]) * float(score)
        for name, score in score_by_interruption.items()
    )


def per_hand_outcome_rows(
    reports: Mapping[str, Mapping[str, Any]],
    *,
    baseline: str = "none",
    interruption_weights: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Join interruption reports by opening hand into outcome metrics."""
    by_hand: dict[tuple[int, ...], dict[str, Mapping[str, Any]]] = {}
    for name, report in reports.items():
        for row in report.get("hands", ()):
            key = tuple(int(card) for card in row["hand"])
            by_hand.setdefault(key, {})[name] = row

    outcomes: list[dict[str, Any]] = []
    for hand, scenarios in by_hand.items():
        if baseline not in scenarios:
            continue
        baseline_row = scenarios[baseline]
        utilities = {name: float(row["score"]) for name, row in scenarios.items()}
        losses = {
            name: interruption_loss(utilities, name, baseline=baseline)
            for name in utilities
            if name != baseline
        }
        outcome: dict[str, Any] = {
            "hand": list(hand),
            "probability": float(baseline_row["probability"]),
            "classification": baseline_row.get("classification") or {},
            "ceiling": ceiling(utilities, baseline=baseline),
            "utilities": utilities,
            "floor_over_configured_interruptions": floor_over_configured(utilities),
            "interruption_loss": losses,
            "complete": all(bool(row.get("complete")) for row in scenarios.values()),
            # Row shape compatible with summarize_rows / utility_distribution
            # when analyzing floor as the scored outcome.
            "score": floor_over_configured(utilities),
            "categories": baseline_row.get("categories") or {
                category: 0.0 for category in SCORE_CATEGORIES
            },
        }
        if interruption_weights is not None:
            try:
                outcome["expected_utility"] = expected_utility(
                    utilities, interruption_weights
                )
            except ValueError:
                outcome["expected_utility"] = None
                outcome["expected_utility_note"] = (
                    "Not computed: interruption weights do not cover all "
                    "evaluated scenarios."
                )
        outcomes.append(outcome)
    return outcomes


def hand_feature_access_rates(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Input-composition rates among evaluated hands (not solver success)."""
    mass = sum(float(row.get("probability", 0.0)) for row in rows)
    features = {
        "starter_access": ("starter", "ge", 1),
        "extender_access": ("extender", "ge", 1),
        "interaction_access": ("interaction", "ge", 1),
        "recovery_access": ("recovery", "ge", 1),
        "brick_free": ("brick", "eq", 0),
    }
    result: dict[str, Any] = {
        "layer": "hand_features",
        "note": (
            "These rates describe role composition among evaluated hands. "
            "They are not playability or success rates."
        ),
        "evaluated_probability_mass": mass,
        "rates": {},
    }
    if mass <= 0:
        for name, (role, kind, threshold) in features.items():
            op = ">=" if kind == "ge" else "="
            result["rates"][name] = {
                "predicate": f"{role}_count {op} {threshold}",
                "probability_mass": 0.0,
                "evaluated_sample_rate": None,
            }
        return result

    for name, (role, kind, threshold) in features.items():
        matched_mass = sum(
            float(row["probability"])
            for row in rows
            if count_matches(role_count(row, role), kind, threshold)
        )
        op = ">=" if kind == "ge" else "="
        result["rates"][name] = {
            "predicate": f"{role}_count {op} {threshold}",
            "probability_mass": matched_mass,
            "evaluated_sample_rate": matched_mass / mass,
        }
    return result


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
    joint = summarize_joint_conditions(rows, joint_conditions)
    return {
        "sampling": sampling_context(rows),
        "by_role": by_role,
        "joint": joint,
        "conditional_bucket_deltas": {
            "starter_extender": conditional_bucket_deltas(joint, JOINT_DELTA_ORDER),
            "kind": "conditional_association",
            "note": (
                "Adjacent joint-bucket score differences are observational. "
                "Use extender counterfactual replacement for interventional "
                "card contribution."
            ),
        },
    }


def quantified_hand_report(
    reports: Mapping[str, Mapping[str, Any]],
    *,
    thresholds: Sequence[float] | None = None,
    interruption_weights: Mapping[str, float] | None = None,
    baseline: str = "none",
) -> dict[str, Any]:
    """Going-first-compatible report separating hand features from outcomes.

    Operates generically on interruption-keyed row reports; turn-order is a
    property of the rows, not of this math.
    """
    thresholds = tuple(DEFAULT_SUCCESS_THRESHOLDS if thresholds is None else thresholds)
    baseline_rows = list((reports.get(baseline) or {}).get("hands") or ())
    outcomes = per_hand_outcome_rows(
        reports, baseline=baseline, interruption_weights=interruption_weights
    )
    floor_rows = [
        {
            "probability": row["probability"],
            "score": row["floor_over_configured_interruptions"],
            "categories": row["categories"],
            "complete": row["complete"],
            "classification": row["classification"],
        }
        for row in outcomes
    ]

    by_interruption: dict[str, Any] = {}
    for name, report in reports.items():
        rows = list(report.get("hands") or ())
        by_interruption[name] = {
            "layer": "solver_outcomes",
            "utility_distribution": utility_distribution(rows, thresholds),
            "summary": summarize_rows(rows),
            "conditioned": conditioned_hand_utility(rows),
        }

    expected_block: dict[str, Any] | None = None
    if interruption_weights is not None and outcomes:
        expected_rows = [
            {
                "probability": row["probability"],
                "score": row["expected_utility"],
                "categories": row["categories"],
                "complete": row["complete"],
                "classification": row["classification"],
            }
            for row in outcomes
            if row.get("expected_utility") is not None
        ]
        if expected_rows:
            expected_block = {
                "definition": "ExpectedUtility(H) = sum_i P(i) U(H, i)",
                "interruption_weights": dict(interruption_weights),
                "utility_distribution": utility_distribution(expected_rows, thresholds),
            }

    return {
        "terminology": {
            "principle": (
                "Every analytical term maps to an observable quantity, "
                "explicit mathematical function, or configurable predicate."
            ),
            "hand_features": "Role counts and overlaps (input composition).",
            "solver_outcomes": "U(H, I) and category scores from search.",
            "ceiling": "Ceiling(H) = U(H, no_interruption).",
            "interruption_loss": "Loss(H, I) = Ceiling(H) - U(H, I).",
            "floor": (
                "Floor(H) = min_i U(H, i) over the configured/evaluated "
                "interruption set only."
            ),
            "playable_at_threshold": (
                "Playable_T(H, I) := U(H, I) >= T with T explicit/configurable."
            ),
            "conditional_association_vs_counterfactual": (
                "Bucket deltas are observational associations. Extender "
                "replacement analysis is the interventional counterpart."
            ),
        },
        "sampling": sampling_context(baseline_rows),
        "success_thresholds": [float(threshold) for threshold in thresholds],
        "hand_features": hand_feature_access_rates(baseline_rows),
        "solver_outcomes": {
            "by_interruption": by_interruption,
            "floor_over_configured_interruptions": {
                "definition": (
                    "Floor(H) = min over configured interruptions of U(H, i)"
                ),
                "utility_distribution": utility_distribution(floor_rows, thresholds),
                "summary": summarize_rows(floor_rows),
            },
            "expected_utility": expected_block,
        },
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
