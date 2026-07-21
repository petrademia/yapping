from yapping import EndboardEvaluator, EvaluationState


def test_baseline_delta_shape_is_additive():
    baseline = {"board_value": 8.0, "interaction_value": 2.0,
                "follow_up_value": 3.0, "survival_value": 1.0}
    interrupted = {"board_value": 5.0, "interaction_value": 1.0,
                   "follow_up_value": 2.0, "survival_value": 0.0}
    delta = {key: baseline[key] - interrupted[key] for key in baseline}
    assert delta == {"board_value": 3.0, "interaction_value": 1.0,
                     "follow_up_value": 1.0, "survival_value": 1.0}


def test_evaluator_scores_identity_by_location_and_state():
    evaluator = EndboardEvaluator(
        {10: 5.0, 20: 2.0},
        {"card_advantage": 0.25, "disruption_survived": 3.0},
    )
    state = EvaluationState(
        {"monster": (10,), "spell_trap": (20,), "hand": (10,), "grave": ()},
        {"opponent_interrupted": True},
    )
    assert evaluator.breakdown(state) == {
        "generic_hand": 0.25,
        "monsters": 5.0,
        "spell_traps": 2.0,
        "named_hand_followup": 5.0,
        "grave_resources": 0.0,
        "survival": 3.0,
    }
    assert evaluator.categories(state) == {
        "board_value": 5.0,
        "interaction_value": 2.0,
        "follow_up_value": 5.25,
        "survival_value": 3.0,
        "total_score": 15.25,
    }
