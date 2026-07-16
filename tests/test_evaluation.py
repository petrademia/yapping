from yapping import EndboardEvaluator, EvaluationState


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
