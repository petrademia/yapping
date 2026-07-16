import json
from pathlib import Path

from yapping.card_rules import CardDatabase

ROOT = Path(__file__).parents[1]

def test_card_database_identifies_high_spirits_races_and_targets():
    config = json.loads((ROOT / "configs/branded_albaz_v1.json").read_text())
    cards = CardDatabase(ROOT / "assets/cards.cdb")
    cartesia = cards.card(95515789)
    fallen_albaz = cards.card(68468459)
    kitt = cards.card(19304410)
    fuwalos = cards.card(42141493)
    assert cartesia.race != fallen_albaz.race
    assert kitt.race == 16384  # RACE_BEAST
    assert fuwalos.race == 512  # RACE_WINGEDBEAST
    targets = cards.high_spirits_targets(95515789, config["extra_deck"])
    assert any(target.name == "Granguignol the Dusk Dragon" for target in targets)
    assert any(target.name == "Albion the Branded Dragon" for target in cards.high_spirits_targets(68468459, config["extra_deck"]))
    assert any(target.name == "The Dragon that Devours the Dogma" for target in cards.high_spirits_targets(19304410, config["extra_deck"]))
    assert any(target.name == "Rindbrumm the Striking Dragon" for target in cards.high_spirits_targets(42141493, config["extra_deck"]))
