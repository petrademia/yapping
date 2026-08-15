"""Portable tests for quantified hand-utility analysis (no OCGCore)."""

import pytest

from yapping.consistency import (
    HandCondition,
    ceiling,
    conditional_bucket_deltas,
    conditioned_hand_utility,
    count_matches,
    empty_bucket_summary,
    expected_utility,
    floor_over_configured,
    hand_feature_access_rates,
    interruption_loss,
    predicate_from_clauses,
    predicate_from_conditions,
    quantified_hand_report,
    role_count,
    role_density_opening_profile,
    sampling_context,
    summarize_by_predicate,
    summarize_joint_conditions,
    summarize_role_counts,
    summarize_rows,
    utility_distribution,
    weighted_quantile,
)
from yapping.roles import normalize_card_roles


def _row(
    *,
    probability,
    score,
    hand=None,
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
        "hand": list(hand or []),
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
    assert buckets["=0"]["evaluated_hands"] == 1
    assert buckets["=1"]["evaluated_hands"] == 1
    assert buckets[">=3"]["evaluated_hands"] == 1
    assert buckets["=2"]["evaluated_hands"] == 0
    assert buckets["=2"]["normalized_weighted_score"] is None


def test_weighted_conditional_mean_uses_probabilities():
    rows = [
        _row(probability=0.1, score=2.0, starter=1, extender=1),
        _row(probability=0.3, score=8.0, starter=1, extender=1),
    ]
    summary = summarize_by_predicate(
        rows, predicate_from_clauses((("starter", "ge", 1), ("extender", "eq", 1)))
    )
    assert summary["probability_mass"] == pytest.approx(0.4)
    assert summary["normalized_weighted_score"] == pytest.approx(6.5)


def test_bucket_probability_mass_and_share_of_evaluated():
    rows = [
        _row(probability=0.2, score=4.0, extender=0),
        _row(probability=0.1, score=7.0, extender=1),
        _row(probability=0.05, score=9.0, extender=2),
    ]
    context = sampling_context(rows)
    assert context["covers_full_deck_distribution"] is False
    assert context["evaluated_probability_mass"] == pytest.approx(0.35)
    assert context["evaluated_probability_mass"] < 1.0
    buckets = summarize_role_counts(rows, "extender")
    assert buckets["=0"]["probability_mass"] == pytest.approx(0.2)
    assert buckets["=0"]["mass_share_of_evaluated"] == pytest.approx(0.2 / 0.35)


def test_empty_bucket_behavior():
    assert empty_bucket_summary()["normalized_weighted_score"] is None
    rows = [_row(probability=0.2, score=3.0, extender=1)]
    buckets = summarize_role_counts(rows, "extender")
    assert buckets["=0"]["hands"] == 0
    assert buckets["=0"]["weighted_score"] is None


def test_joint_starter_and_extender_condition():
    rows = [
        _row(probability=0.1, score=1.0, starter=0, extender=1),
        _row(probability=0.2, score=8.0, starter=1, extender=1),
        _row(probability=0.05, score=3.0, starter=1, extender=0),
    ]
    joint = summarize_joint_conditions(rows)
    assert joint["starter>=1,extender=1"]["hands"] == 1
    assert joint["starter>=1,extender=1"]["normalized_weighted_score"] == pytest.approx(8.0)
    alone = summarize_role_counts(rows, "extender")["=1"]
    assert alone["hands"] == 2


def test_hand_condition_composes_like_clauses():
    rows = [
        _row(probability=0.2, score=7.0, starter=1, extender=1),
        _row(probability=0.2, score=2.0, starter=0, extender=1),
    ]
    predicate = predicate_from_conditions((
        HandCondition("starter", ">=", 1),
        HandCondition("extender", "=", 1),
    ))
    summary = summarize_by_predicate(rows, predicate)
    assert summary["evaluated_hands"] == 1
    assert summary["normalized_weighted_score"] == pytest.approx(7.0)


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
        _row(probability=0.1, score=9.0, starter=1, extender=0),
    ]
    summary = summarize_joint_conditions(rows)["starter>=1,extender=1"]
    assert summary["paired_hands"] == 2
    assert abs(summary["weighted_score_loss"] - 3.0) < 1e-9


def test_overlapping_roles_in_input_rows():
    row = _row(probability=0.1, score=5.0, starter=1, extender=1, recovery=1)
    assert role_count(row, "starter") == 1
    assert role_count(row, "extender") == 1
    assert role_count(row, "recovery") == 1


def test_threshold_success_rate_exposes_threshold():
    rows = [
        _row(probability=0.1, score=4.0),
        _row(probability=0.3, score=12.0),
    ]
    distribution = utility_distribution(rows, thresholds=(5, 10, 15))
    assert distribution["thresholds"]["5"]["threshold"] == 5.0
    assert distribution["thresholds"]["5"]["predicate"] == "U >= 5.0"
    assert distribution["thresholds"]["5"]["probability_mass"] == pytest.approx(0.3)
    assert distribution["thresholds"]["5"]["evaluated_sample_success_rate"] == pytest.approx(0.75)
    assert distribution["thresholds"]["10"]["evaluated_sample_success_rate"] == pytest.approx(0.75)
    assert distribution["thresholds"]["15"]["evaluated_sample_success_rate"] == pytest.approx(0.0)
    assert distribution["covers_full_deck_distribution"] is False
    assert distribution["evaluated_probability_mass"] == pytest.approx(0.4)


def test_weighted_quantiles():
    rows = [
        _row(probability=0.1, score=1.0),
        _row(probability=0.4, score=5.0),
        _row(probability=0.5, score=9.0),
    ]
    assert weighted_quantile(rows, 0.0) == pytest.approx(1.0)
    assert weighted_quantile(rows, 0.10) == pytest.approx(1.0)
    assert weighted_quantile(rows, 0.50) == pytest.approx(5.0)
    assert weighted_quantile(rows, 0.90) == pytest.approx(9.0)
    distribution = utility_distribution(rows, thresholds=(5,))
    assert distribution["weighted_median"] == pytest.approx(5.0)
    assert distribution["weighted_mean"] == pytest.approx(0.1 * 1 + 0.4 * 5 + 0.5 * 9)


def test_ceiling_floor_and_interruption_loss():
    utilities = {"none": 10.0, "ash": 6.0, "impermanence": 4.0}
    assert ceiling(utilities) == 10.0
    assert interruption_loss(utilities, "ash") == 4.0
    assert floor_over_configured(utilities) == 4.0
    assert expected_utility(utilities, {"none": 0.5, "ash": 0.25, "impermanence": 0.25}) == pytest.approx(7.5)
    with pytest.raises(ValueError):
        expected_utility(utilities, {"none": 1.0})


def test_conditional_bucket_deltas_are_observational():
    rows = [
        _row(probability=0.2, score=4.0, starter=1, extender=0),
        _row(probability=0.2, score=8.0, starter=1, extender=1),
        _row(probability=0.2, score=9.0, starter=1, extender=2),
    ]
    joint = summarize_joint_conditions(rows)
    deltas = conditional_bucket_deltas(
        joint,
        (
            "starter>=1,extender=0",
            "starter>=1,extender=1",
            "starter>=1,extender=2",
        ),
    )
    first = deltas["starter>=1,extender=1_minus_starter>=1,extender=0"]
    assert first["kind"] == "conditional_association"
    assert first["normalized_weighted_score_delta"] == pytest.approx(4.0)
    assert "counterfactual" in first["note"].lower() or "observational" in first["note"].lower()


def test_hand_feature_access_not_playability():
    rows = [
        _row(probability=0.2, score=1.0, starter=1, extender=0),  # starter but low U
        _row(probability=0.2, score=12.0, starter=0, extender=1),
    ]
    features = hand_feature_access_rates(rows)
    assert features["layer"] == "hand_features"
    assert features["rates"]["starter_access"]["evaluated_sample_rate"] == pytest.approx(0.5)
    # Low-score starter hand must not be called playable by feature rates.
    distribution = utility_distribution(rows, thresholds=(10,))
    assert distribution["thresholds"]["10"]["evaluated_sample_success_rate"] == pytest.approx(0.5)


def test_quantified_hand_report_separates_layers():
    reports = {
        "none": {
            "hands": [
                _row(probability=0.2, score=10.0, hand=[1, 2], starter=1, extender=0),
                _row(probability=0.1, score=8.0, hand=[3, 4], starter=1, extender=1),
            ]
        },
        "ash": {
            "hands": [
                _row(
                    probability=0.2, score=6.0, hand=[1, 2], starter=1, extender=0,
                    score_loss=4.0,
                ),
                _row(
                    probability=0.1, score=7.0, hand=[3, 4], starter=1, extender=1,
                    score_loss=1.0,
                ),
            ]
        },
    }
    report = quantified_hand_report(reports, thresholds=(5, 10))
    assert "hand_features" in report
    assert "solver_outcomes" in report
    assert report["success_thresholds"] == [5.0, 10.0]
    assert report["sampling"]["covers_full_deck_distribution"] is False
    floor = report["solver_outcomes"]["floor_over_configured_interruptions"]
    assert floor["utility_distribution"]["weighted_mean"] == pytest.approx(
        (0.2 * 6.0 + 0.1 * 7.0) / 0.3
    )
    ash = report["solver_outcomes"]["by_interruption"]["ash"]
    assert ash["utility_distribution"]["thresholds"]["5"]["threshold"] == 5.0
    deltas = ash["conditioned"]["conditional_bucket_deltas"]["starter_extender"]
    assert "starter>=1,extender=1_minus_starter>=1,extender=0" in deltas


def test_conditioned_hand_utility_schema_and_role_density():
    rows = [
        _row(probability=0.1, score=4.0, starter=1, extender=0),
        _row(probability=0.2, score=8.0, starter=1, extender=1),
    ]
    report = conditioned_hand_utility(rows)
    assert report["sampling"]["covers_full_deck_distribution"] is False
    assert "extender" in report["by_role"]
    assert "starter>=1,extender=1" in report["joint"]
    assert report["joint"]["starter>=1,extender=1"]["normalized_weighted_score"] == pytest.approx(8.0)
    assert "conditional_bucket_deltas" in report

    roles = normalize_card_roles({"1": ["starter"], "2": ["extender"], "3": ["extender"]})
    deck = [1, 1, 2, 2, 2, 9, 9, 9, 9, 9]
    profile = role_density_opening_profile(
        deck, roles, roles=["starter", "extender"], hand_size=2
    )
    assert profile["starter"]["role_copies_in_deck"] == 2
    assert abs(sum(profile["extender"]["opening_count_probability"].values()) - 1.0) < 1e-12
