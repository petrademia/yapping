"""Portable tests for conditioned hand-utility aggregation (no OCGCore)."""

import pytest

from yapping.consistency import (
    conditioned_hand_utility,
    count_matches,
    empty_bucket_summary,
    predicate_from_clauses,
    role_count,
    role_density_opening_profile,
    sampling_context,
    summarize_by_predicate,
    summarize_joint_conditions,
    summarize_role_counts,
    summarize_rows,
)
from yapping.roles import normalize_card_roles


def _row(
    *,
    probability,
    score,
    starter=0,
    extender=0,
    interaction=0,
    brick=0,
    recovery=0,
    complete=True,
    score_loss=None,
    board=0.0,
    interaction_value=0.0,
    follow_up=0.0,
    survival=0.0,
):
    role_counts = {
        role: amount
        for role, amount in {
            "starter": starter,
            "extender": extender,
            "interaction": interaction,
            "brick": brick,
            "recovery": recovery,
        }.items()
        if amount
    }
    classification = {
        "brick": starter == 0,
        "garnets": [],
        "role_counts": role_counts,
        "roles_present": sorted(role_counts),
        "role_overlaps": {},
    }
    for role, amount in {
        "starter": starter,
        "extender": extender,
        "interaction": interaction,
        "brick": brick,
        "recovery": recovery,
    }.items():
        classification[f"{role}_count"] = amount
    row = {
        "hand": [],
        "probability": probability,
        "classification": classification,
        "score": score,
        "categories": {
            "board_value": board,
            "interaction_value": interaction_value,
            "follow_up_value": follow_up,
            "survival_value": survival,
        },
        "complete": complete,
    }
    if score_loss is not None:
        row["score_loss"] = score_loss
        row["category_deltas"] = {
            "board_value": score_loss,
            "interaction_value": 0.0,
            "follow_up_value": 0.0,
            "survival_value": 0.0,
        }
    return row


def test_role_count_bucket_assignment_and_ge():
    assert count_matches(0, "eq", 0)
    assert count_matches(3, "ge", 3)
    assert not count_matches(2, "ge", 3)
    rows = [
        _row(probability=0.1, score=1.0, extender=0),
        _row(probability=0.2, score=5.0, extender=1),
        _row(probability=0.05, score=9.0, extender=4),
    ]
    buckets = summarize_role_counts(rows, "extender")
    assert buckets["=0"]["hands"] == 1
    assert buckets["=1"]["hands"] == 1
    assert buckets[">=3"]["hands"] == 1
    assert buckets["=2"]["hands"] == 0
    assert buckets["=2"]["weighted_score"] is None


def test_weighted_conditional_mean_uses_probabilities():
    # Equal arithmetic mean would be (2+8)/2 = 5, but mass-weighted is
    # (0.1*2 + 0.3*8) / 0.4 = 6.5
    rows = [
        _row(probability=0.1, score=2.0, starter=1, extender=1),
        _row(probability=0.3, score=8.0, starter=1, extender=1),
    ]
    summary = summarize_by_predicate(
        rows, predicate_from_clauses((("starter", "ge", 1), ("extender", "eq", 1)))
    )
    assert summary["probability_mass"] == 0.4
    assert summary["weighted_score"] == 6.5
    assert summary["weighted_categories"]["board_value"] == 0.0


def test_bucket_probability_mass_and_share_of_evaluated():
    rows = [
        _row(probability=0.2, score=4.0, extender=0),
        _row(probability=0.1, score=7.0, extender=1),
        _row(probability=0.05, score=9.0, extender=2),
    ]
    context = sampling_context(rows)
    assert context["covers_full_deck_distribution"] is False
    assert context["raw_probability_mass"] == pytest.approx(0.35)
    assert context["evaluated_hands"] == 3
    buckets = summarize_role_counts(rows, "extender")
    assert buckets["=0"]["probability_mass"] == pytest.approx(0.2)
    assert buckets["=0"]["mass_share_of_evaluated"] == pytest.approx(0.2 / 0.35)
    # Sample mass is not presented as 100% coverage of the deck.
    assert sum(b["probability_mass"] for b in buckets.values()) == pytest.approx(0.35)
    assert context["raw_probability_mass"] < 1.0


def test_empty_bucket_behavior():
    assert empty_bucket_summary()["weighted_score"] is None
    rows = [_row(probability=0.2, score=3.0, extender=1)]
    buckets = summarize_role_counts(rows, "extender")
    assert buckets["=0"] == empty_bucket_summary() | {
        "mass_share_of_evaluated": 0.0,
    }
    assert buckets["=0"]["hands"] == 0


def test_joint_starter_and_extender_condition():
    rows = [
        _row(probability=0.1, score=1.0, starter=0, extender=1),
        _row(probability=0.2, score=8.0, starter=1, extender=1),
        _row(probability=0.05, score=3.0, starter=1, extender=0),
    ]
    joint = summarize_joint_conditions(rows)
    assert joint["starter>=1,extender=1"]["hands"] == 1
    assert joint["starter>=1,extender=1"]["weighted_score"] == pytest.approx(8.0)
    assert joint["starter>=1,extender=0"]["weighted_score"] == pytest.approx(3.0)
    # Extender=1 alone would mix the starterless hand; joint excludes it.
    alone = summarize_role_counts(rows, "extender")["=1"]
    assert alone["hands"] == 2
    assert alone["weighted_score"] == pytest.approx((0.1 * 1.0 + 0.2 * 8.0) / 0.3)


def test_complete_fraction_preserves_provisional_rows():
    rows = [
        _row(probability=0.4, score=5.0, starter=1, extender=1, complete=True),
        _row(probability=0.1, score=2.0, starter=1, extender=1, complete=False),
    ]
    summary = summarize_rows(rows)
    assert summary["complete_fraction"] == 0.5
    assert summary["provisional_hands"] == 1


def test_conditional_score_loss_aggregation():
    rows = [
        _row(probability=0.2, score=6.0, starter=1, extender=1, score_loss=2.0),
        _row(probability=0.2, score=4.0, starter=1, extender=1, score_loss=4.0),
        _row(probability=0.1, score=9.0, starter=1, extender=0),  # no loss field
    ]
    summary = summarize_joint_conditions(rows)["starter>=1,extender=1"]
    assert summary["paired_hands"] == 2
    assert abs(summary["weighted_score_loss"] - 3.0) < 1e-9
    assert abs(summary["weighted_category_loss"]["board_value"] - 3.0) < 1e-9


def test_overlapping_roles_in_input_rows():
    # Multi-label input already encoded as separate counts; one card may raise both.
    row = _row(probability=0.1, score=5.0, starter=1, extender=1, recovery=1)
    assert role_count(row, "starter") == 1
    assert role_count(row, "extender") == 1
    assert role_count(row, "recovery") == 1


def test_conditioned_hand_utility_schema_and_role_density():
    rows = [
        _row(probability=0.1, score=4.0, starter=1, extender=0),
        _row(probability=0.2, score=8.0, starter=1, extender=1),
    ]
    report = conditioned_hand_utility(rows)
    assert report["sampling"]["covers_full_deck_distribution"] is False
    assert "extender" in report["by_role"]
    assert "starter>=1,extender=1" in report["joint"]
    assert report["joint"]["starter>=1,extender=1"]["weighted_score"] == 8.0

    roles = normalize_card_roles({"1": ["starter"], "2": ["extender"], "3": ["extender"]})
    deck = [1, 1, 2, 2, 2, 9, 9, 9, 9, 9]
    profile = role_density_opening_profile(deck, roles, roles=["starter", "extender"], hand_size=2)
    assert profile["starter"]["role_copies_in_deck"] == 2
    assert profile["extender"]["role_copies_in_deck"] == 3
    assert abs(sum(profile["extender"]["opening_count_probability"].values()) - 1.0) < 1e-12
