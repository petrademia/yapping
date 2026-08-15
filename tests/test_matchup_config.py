from matchup_config import load_config, scenarios
from analyze_consistency import classify


def test_scenarios_normalize_weights_and_names():
    worlds = scenarios({"matchup_scenarios": [
        {"name": "clean", "interruption": "none", "weight": 3},
        {"interruption": "ash", "weight": 1},
    ]})
    assert [world["name"] for world in worlds] == ["clean", "ash"]
    assert [world["weight"] for world in worlds] == [0.75, 0.25]


def test_scenarios_support_requested_interruptions():
    worlds = scenarios({}, ["none", "veiler"])
    assert [world["interruption"] for world in worlds] == ["none", "veiler"]


def test_consistency_classify_adds_role_counts_from_albaz_config():
    config = load_config()
    hand = [73819701, 55273560, 95515789, 91152256, 91152256]
    result = classify(hand, config)
    assert result["brick"] is False
    assert result["starter_count"] == 2
    assert result["extender_count"] == 2
    assert result["recovery_count"] == 1
    assert "role_counts" in result
    assert result["role_overlaps"]["55273560"] == ["extender", "recovery", "starter"]
