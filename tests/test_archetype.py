from pathlib import Path

from yapping import load_archetype, load_combo, summarize_compendium
from yapping.variants import SlotCandidate

ROOT = Path(__file__).parents[1]


def test_branded_config_is_the_generic_archetype_boundary():
    archetype = load_archetype(ROOT / "configs/archetypes/branded.json")
    assert archetype.name == "branded_albaz_v1"
    assert archetype.card_weights[44146295] == 10.0
    assert sum(archetype.deck_counts.values()) == 47
    assert archetype.deck_counts[62962630] == 3
    assert archetype.extra_deck_counts[24915933] == 1
    assert archetype.interruptions["ash"].card_id == 14558127
    assert archetype.interruptions["ash"].policy == "activate_at_first_legal_search"
    assert archetype.target_predicates["high_spirits"]["same_race_as"] == "revealed_hand_card"
    assert {fixture.id for fixture in archetype.fixtures} == {"mdm-one-card-fallen", "mdm-high-spirits", "mdm-fallen-white-dragon-droll-recovery"}
    assert all(fixture.path.is_file() for fixture in archetype.fixtures)


def test_compendium_marks_known_candidate_cards():
    archetype = load_archetype(ROOT / "configs/archetypes/branded.json")
    report = summarize_compendium(archetype, [SlotCandidate(44146295, "board_breaker", "Mirrorjade")])
    assert report["verified_fixtures"] == 3
    assert report["candidates"]["44146295"]["known_to_compendium"] is True


def test_combo_catalog_resolves_against_card_database():
    combo = load_combo(ROOT / "configs/combos/master_duel_meta_branded.json",
                       ROOT / "assets/cards.cdb")
    assert combo["card_ids"]["Fallen of the White Dragon"] == 73819701
