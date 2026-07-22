from matchup_config import scenarios


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
