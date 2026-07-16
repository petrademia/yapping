import json
from pathlib import Path
import pytest

from yapping.card_rules import CardDatabase
from yapping import load_archetype

ROOT = Path(__file__).parents[1]


@pytest.mark.skipif(not (ROOT / "assets/cards.cdb").is_file(), reason="card database is not installed")
def test_card_database_identifies_high_spirits_races_and_targets():
    archetype = load_archetype(ROOT / "configs/archetypes/branded.json")
    cards = CardDatabase(ROOT / "assets/cards.cdb")
    cartesia = cards.card(95515789)
    fallen_albaz = cards.card(68468459)
    kitt = cards.card(19304410)
    fuwalos = cards.card(42141493)
    assert cartesia.race != fallen_albaz.race
    assert kitt.race == 16384  # RACE_BEAST
    assert fuwalos.race == 512  # RACE_WINGEDBEAST
    predicate = archetype.target_predicates["high_spirits"]
    targets = cards.matching_targets(95515789, list(archetype.extra_deck), predicate)
    assert any(target.name == "Granguignol the Dusk Dragon" for target in targets)
    assert any(target.name == "Albion the Branded Dragon" for target in cards.matching_targets(68468459, list(archetype.extra_deck), predicate))
    assert any(target.name == "The Dragon that Devours the Dogma" for target in cards.matching_targets(19304410, list(archetype.extra_deck), predicate))
    assert any(target.name == "Rindbrumm the Striking Dragon" for target in cards.matching_targets(42141493, list(archetype.extra_deck), predicate))
