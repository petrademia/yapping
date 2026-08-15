from pathlib import Path

import pytest

from yapping import (
    cards_with_role,
    count_roles,
    hand_features,
    load_archetype,
    normalize_card_roles,
    opening_at_least_probability,
    opening_count_probability,
    opening_probability,
    roles_for,
)
from yapping.archetype import Archetype
from yapping.roles import role_copies_in_deck

ROOT = Path(__file__).parents[1]


def test_archetype_without_card_roles_remains_valid(tmp_path):
    path = tmp_path / "bare.json"
    path.write_text(
        '{"name": "bare", "main_deck": [1, 2], "extra_deck": [], '
        '"interruption_specs": {}, "fixtures": [], '
        '"target_predicates": {}, "card_weights": {}, "objectives": {}}',
        encoding="utf-8",
    )
    archetype = load_archetype(path)
    assert archetype.card_roles == {}
    assert archetype.roles_for(1) == frozenset()


def test_branded_card_roles_normalize_string_ids():
    archetype = load_archetype(ROOT / "configs/archetypes/branded.json")
    assert isinstance(next(iter(archetype.card_roles)), int)
    assert "starter" in archetype.roles_for(73819701)
    assert archetype.roles_for(55273560) == frozenset(
        {"starter", "extender", "recovery"}
    )
    assert 55273560 in archetype.cards_with_role("extender")
    assert 55273560 in archetype.cards_with_role("recovery")


def test_normalize_card_roles_accepts_string_keys_and_overlap():
    roles = normalize_card_roles({
        "10": ["starter", "extender"],
        20: "interaction",
    })
    assert roles[10] == frozenset({"starter", "extender"})
    assert roles[20] == frozenset({"interaction"})
    assert roles_for(roles, 10) == frozenset({"starter", "extender"})
    assert cards_with_role(roles, "starter") == frozenset({10})


def test_hand_role_counts_handle_overlaps_and_duplicates():
    roles = normalize_card_roles({
        "1": ["starter", "extender"],
        "2": ["extender"],
        "3": ["interaction"],
    })
    hand = [1, 1, 2, 3]
    assert count_roles(hand, roles) == {
        "extender": 3,
        "interaction": 1,
        "starter": 2,
    }
    features = hand_features(hand, roles)
    assert features["roles_present"] == ["extender", "interaction", "starter"]
    assert features["role_overlaps"] == {"1": ["extender", "starter"]}
    assert role_copies_in_deck([1, 1, 2, 9], roles, "extender") == 3


def test_opening_probability_unchanged():
    assert opening_probability(40, 3, 5) == pytest.approx(0.3375506073)


def test_opening_count_and_at_least_boundaries():
    exactly_zero = opening_count_probability(40, 3, 5, 0)
    at_least_one = opening_at_least_probability(40, 3, 5, 1)
    assert exactly_zero + at_least_one == pytest.approx(1.0)
    assert at_least_one == pytest.approx(opening_probability(40, 3, 5))
    assert opening_count_probability(40, 3, 5, 5) == 0.0
    assert opening_count_probability(40, 0, 5, 0) == 1.0
    assert opening_at_least_probability(40, 3, 5, 0) == 1.0
    assert opening_at_least_probability(40, 0, 5, 1) == 0.0


def test_archetype_dataclass_defaults_empty_roles():
    archetype = Archetype(
        name="x",
        main_deck=(1,),
        extra_deck=(),
        interruptions={},
        fixtures=(),
        target_predicates={},
        card_weights={},
        objectives={},
        metadata={},
    )
    assert archetype.card_roles == {}
