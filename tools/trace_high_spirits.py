import json
from pathlib import Path

from trace_albaz_combo import new_duel, BLAZING_CARTESIA

from yapping.card_rules import CardDatabase

ROOT = Path(__file__).parents[1]
HIGH_SPIRITS = 29948294
GRANGUIGNOL = 24915933
FALLEN_WHITE = 73819701
BRANDED_RED = 82738008
BRANDED_FUSION = 44362883
FORBIDDEN_CROWN = 98829635

def choose(duel, decision, kind, card=None):
    for index, action in enumerate(decision["actions"]):
        if action["kind"] == kind and (card is None or action["card"] == card):
            return duel.step(index)
    raise RuntimeError(f"missing {kind} {card}: {decision['actions']}")

def main():
    config = json.loads((ROOT / "configs/branded_albaz_v1.json").read_text())
    hand = [HIGH_SPIRITS, BLAZING_CARTESIA, BRANDED_RED, BRANDED_FUSION, FORBIDDEN_CROWN]
    duel, decision = new_duel(
        opening_hand=hand,
        main_deck=config["main_deck"],
        extra_deck=config["extra_deck"],
    )
    decision = choose(duel, decision, "chain", HIGH_SPIRITS)
    decision = choose(duel, decision, "place")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "select_card", BLAZING_CARTESIA)
    decision = choose(duel, decision, "select_card", GRANGUIGNOL)
    decision = choose(duel, decision, "yes")
    decision = choose(duel, decision, "select_card", FALLEN_WHITE)
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "activate", FALLEN_WHITE)
    decision = choose(duel, decision, "select_card", 87746184)
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "place")
    decision = choose(duel, decision, "position")
    decision = choose(duel, decision, "yes", FALLEN_WHITE)
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "select_card", 55273560)
    decision = choose(duel, decision, "place")
    decision = choose(duel, decision, "position")
    decision = choose(duel, decision, "chain", 55273560)
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    print("ECCLESIA TARGET VALIDATED")
    print("GOLDEN SWORDSOUL TARGET VALIDATED")
    decision = choose(duel, decision, "select_card", 82489470)
    decision = choose(duel, decision, "place")
    decision = choose(duel, decision, "position")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "special_summon", 78397661)
    print("GOLDEN SWORDSOUL TARGET VALIDATED")
    decision = choose(duel, decision, "select_card", 82489470)
    decision = choose(duel, decision, "select_sum", FALLEN_WHITE)
    decision = choose(duel, decision, "place")
    decision = choose(duel, decision, "position")
    print("ECCLESIA DARK SYNCHRO VALIDATED")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    print("ECCLESIA DARK SUMMONED")
    print("ECCLESIA DARK EFFECT VALIDATED")
    decision = choose(duel, decision, "chain", 78397661)
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "select_card", 45883110)
    decision = choose(duel, decision, "place")
    decision = choose(duel, decision, "position")
    print("QUEM SUMMON VALIDATED")
    decision = choose(duel, decision, "chain", 45883110)
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    print("QUEM EFFECT VALIDATED")
    print("QUEM SENDS KITT VALIDATED")
    decision = choose(duel, decision, "select_card", 19304410)
    decision = choose(duel, decision, "yes", 19304410)
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "select_card", FALLEN_WHITE)
    decision = choose(duel, decision, "place")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    print("KITT REVIVES FALLEN VALIDATED")
    print("THREE CHAMPIONS SYNCHRO VALIDATED")
    decision = choose(duel, decision, "special_summon", 74405783)
    decision = choose(duel, decision, "select_card", 45883110)
    decision = choose(duel, decision, "select_sum", FALLEN_WHITE)
    decision = choose(duel, decision, "place")
    decision = choose(duel, decision, "position")
    print("THREE CHAMPIONS SUMMONED")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "yes", 74405783)
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "pass")
    decision = choose(duel, decision, "select_card", 95515789)
    print("THREE CHAMPIONS ADDS CARTESIA", decision["actions"])
    targets = CardDatabase(ROOT / "assets/cards.cdb").high_spirits_targets(
        BLAZING_CARTESIA, config["extra_deck"]
    )
    if not any(target.name == "Granguignol the Dusk Dragon" for target in targets):
        raise RuntimeError("Granguignol was not a legal Spellcaster target")
    print("HIGH SPIRITS TARGETS", [target.name for target in targets])
    print("HIGH SPIRITS FALLEN LINE VALIDATED")
    print(decision["actions"])

if __name__ == "__main__":
    main()
