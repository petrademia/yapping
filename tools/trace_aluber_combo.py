"""Replay the prescribed one-card Aluber line on the configured deck."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from matchup_config import load_config  # noqa: E402
from trace_albaz_combo import (  # noqa: E402
    ALUBER, ALBION_BRANDED, BLAZING_CARTESIA, BRANDED_FUSION, GRANGUIGNOL,
    BRANDED_RETRIBUTION, DEVOURS_DOGMA, FALLEN_VIRTUOUS, FALLEN_WHITE,
    GUIDING_QUEM, INCREDIBLE_ECCLESIA, ROOT, SCRIPTS,
    TRIBRIGADE_SPRINGANS_KITT,
    TITANIKLAD, new_duel,
)
from yapping._ocgcore import Duel  # noqa: E402


CARDS = [
    ALUBER, 14558127, 14558127, 59438930, 59438930,
]
INTERRUPTIONS = {
    "ash": 14558127, "veiler": 97268402, "impermanence": 10045474,
    "droll": 94145021, "nibiru": 27204311, "ghost_ogre": 59438930,
}
INTERRUPTION = os.getenv("YAPPING_ALUBER_INTERRUPTION")
INTERRUPTION_CARD = INTERRUPTIONS.get(INTERRUPTION)
INTERRUPTION_USED = False


def action(decision, kind, card=None):
    for index, candidate in enumerate(decision["actions"]):
        if candidate["kind"] == kind and (card is None or candidate["card"] == card):
            return index
    raise AssertionError(f"missing {kind} {card}: {decision['actions']}")


def settle(duel, decision):
    while True:
        global INTERRUPTION_USED
        if (INTERRUPTION_CARD is not None and decision["player"] == 1
                and not INTERRUPTION_USED):
            interrupt = next((i for i, candidate in enumerate(decision["actions"])
                              if candidate["kind"] == "chain"
                              and candidate["card"] == INTERRUPTION_CARD), None)
            if interrupt is not None:
                INTERRUPTION_USED = True
                decision = duel.step(interrupt)
                continue
        kinds = {candidate["kind"] for candidate in decision["actions"]}
        kind = next((value for value in ("place", "position", "pass")
                     if value in kinds), None)
        if kind is None:
            return decision
        decision = duel.step(action(decision, kind))


def choose(duel, decision, kind, card=None):
    decision = settle(duel, decision)
    return duel.step(action(decision, kind, card))


def report(duel, interruption, interruption_used, line_complete, recovery):
    zones = {name: duel.cards(0, location) for name, location in {
        "hand": 2, "monster": 4, "spell_trap": 8, "grave": 16, "banished": 32,
    }.items()}
    print(json.dumps({"fixture": "one_card_aluber", "complete": True,
                      "interruption": interruption,
                      "interruption_used": interruption_used,
                      "line_complete": line_complete, "recovery": recovery,
                      "zones": zones}, sort_keys=True))


def main():
    config = load_config("configs/branded_albaz_v1.json")
    adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    duel, decision = new_duel(
        opening_hand=CARDS, main_deck=config["main_deck"],
        extra_deck=config["extra_deck"],
        opponent_card=INTERRUPTION_CARD,
        opponent_set=INTERRUPTION == "impermanence",
        opponent_deck=[BRANDED_RETRIBUTION] * 40, adapter=adapter,
    )
    decision = choose(duel, decision, "summon", ALUBER)
    decision = choose(duel, decision, "yes", ALUBER)
    decision = settle(duel, decision)
    if INTERRUPTION_USED and not any(candidate["kind"] == "select_card"
                                     and candidate["card"] == BRANDED_FUSION
                                     for candidate in decision["actions"]):
        report(duel, INTERRUPTION, INTERRUPTION_USED, False,
               "aluber_search_negated")
        return
    decision = choose(duel, decision, "select_card", BRANDED_FUSION)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "activate", BRANDED_FUSION)
    decision = choose(duel, decision, "select_card", ALBION_BRANDED)
    decision = choose(duel, decision, "select_toggle", BLAZING_CARTESIA)
    decision = choose(duel, decision, "select_toggle", FALLEN_WHITE)
    decision = choose(duel, decision, "yes", ALBION_BRANDED)
    decision = choose(duel, decision, "select_card", GRANGUIGNOL)
    decision = choose(duel, decision, "select_toggle", BLAZING_CARTESIA)
    decision = choose(duel, decision, "select_toggle", ALUBER)
    decision = choose(duel, decision, "yes", GRANGUIGNOL)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", DEVOURS_DOGMA)
    decision = choose(duel, decision, "end_phase")
    decision = settle(duel, decision)
    if INTERRUPTION_USED and not any(candidate["kind"] == "yes"
                                     and candidate["card"] == DEVOURS_DOGMA
                                     for candidate in decision["actions"]):
        report(duel, INTERRUPTION, INTERRUPTION_USED, False,
               "droll_blocks_followup_search")
        return
    decision = choose(duel, decision, "yes", DEVOURS_DOGMA)
    if any(candidate["kind"] == "pass" for candidate in decision["actions"]):
        decision = duel.step(action(decision, "pass"))
    if any(candidate["kind"] == "end_phase" for candidate in decision["actions"]):
        decision = duel.step(action(decision, "end_phase"))
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", FALLEN_VIRTUOUS)
    decision = duel.step(action(decision, "chain", FALLEN_VIRTUOUS))
    decision = choose(duel, decision, "option")
    decision = choose(duel, decision, "select_card", TITANIKLAD)
    decision = choose(duel, decision, "select_card", ALBION_BRANDED)
    while not any(candidate["kind"] == "chain" and candidate["card"] == ALBION_BRANDED
                  for candidate in decision["actions"]):
        if any(candidate["kind"] == "pass" for candidate in decision["actions"]):
            decision = duel.step(action(decision, "pass"))
        else:
            raise AssertionError(f"Albion chain window not reached: {decision['actions']}")
    decision = duel.step(action(decision, "chain", ALBION_BRANDED))
    decision = choose(duel, decision, "select_card", BRANDED_RETRIBUTION)
    decision = duel.step(1)  # set Branded Retribution rather than add it
    decision = choose(duel, decision, "yes", TITANIKLAD)
    decision = choose(duel, decision, "select_card", GUIDING_QUEM)
    decision = duel.step(1)  # special summon rather than add Quem to hand
    decision = settle(duel, decision)
    decision = choose(duel, decision, "yes", GUIDING_QUEM)
    decision = choose(duel, decision, "select_card", TRIBRIGADE_SPRINGANS_KITT)
    decision = choose(duel, decision, "yes", TRIBRIGADE_SPRINGANS_KITT)
    decision = choose(duel, decision, "select_card", FALLEN_WHITE)
    decision = choose(duel, decision, "yes", FALLEN_WHITE)
    decision = choose(duel, decision, "select_card", INCREDIBLE_ECCLESIA)
    decision = settle(duel, decision)
    report(duel, INTERRUPTION, INTERRUPTION_USED, True, "full_line")


if __name__ == "__main__":
    main()
