import os
import json
from pathlib import Path

from yapping._ocgcore import Duel


FALLEN_WHITE = 73819701
TITANIKLAD = 41373230
INCREDIBLE_ECCLESIA = 55273560
GOLDEN_SWORDSOUL = 82489470
ECCLESIA_DARK_DRAGON = 78397661
GUIDING_QUEM = 45883110
TRIBRIGADE_SPRINGANS_KITT = 19304410
THREE_CHAMPIONS = 74405783
BLAZING_CARTESIA = 95515789
ALBION_BRANDED = 87746184
MIRRORJADE = 44146295
DOGMATIKA_ECCLESIA = 60303688
FALLEN_VIRTUOUS = 30271097
DEVOURS_DOGMA = 76666602
MERCOURIER = 19096726
BRANDED_RETRIBUTION = 17751597
CELTIC_GUARDIAN = 91152256
ASH_BLOSSOM = 14558127

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT.parent / "fluorohydride-ygopro-scripts"
ASH_MODE = os.getenv("YAPPING_ASH")
ash_windows = []
current_label = "initial"
action_prefix = []
ash_activated = False


class LineInterrupted(RuntimeError):
    def __init__(self, duel, decision, expected):
        super().__init__(f"missing {expected}")
        self.duel = duel
        self.decision = decision
        self.expected = expected


def step(duel, index):
    action_prefix.append(index)
    return duel.step(index)


def show(label, decision, duel):
    global current_label
    current_label = label
    print(f"\n{label}: player={decision['player']} counts={duel.counts()}")
    for index, action in enumerate(decision["actions"]):
        print(index, action)


def answer_ash(duel, decision):
    global ash_activated
    actions = decision["actions"]
    ash = next((i for i, action in enumerate(actions)
                if action["kind"] == "chain" and action["card"] == ASH_BLOSSOM), None)
    if decision["player"] != 1 or ash is None:
        return None
    window = len(ash_windows)
    ash_windows.append(current_label)
    print(f"ASH WINDOW {window}: {current_label}")
    if ASH_MODE == str(window):
        print(f"ASH ACTIVATE {window}")
        ash_activated = True
        return step(duel, ash)
    return step(duel, next(i for i, action in enumerate(actions) if action["kind"] == "pass"))


def choose(duel, decision, kind, card=None, description=None):
    while True:
        for index, action in enumerate(decision["actions"]):
            if (action["kind"] == kind
                    and (card is None or action["card"] == card)
                    and (description is None or action["description"] == description)):
                return step(duel, index)
        answered = answer_ash(duel, decision)
        if answered is None:
            break
        decision = answered
    if ash_activated:
        raise LineInterrupted(duel, decision, f"{kind} {card}")
    raise RuntimeError(f"missing {kind} {card}")


def settle(duel, decision, stop_on_chain=False):
    while True:
        answered = answer_ash(duel, decision)
        if answered is not None:
            decision = answered
            continue
        kinds = {action["kind"] for action in decision["actions"]}
        if stop_on_chain and "chain" in kinds:
            return decision
        kind = next((kind for kind in ("pass", "place", "position") if kind in kinds), None)
        if kind is None:
            return decision
        decision = choose(duel, decision, kind)
        show(f"after {kind}", decision, duel)


def new_duel(opponent_ash=False):
    filler = [CELTIC_GUARDIAN] * 26
    deck = [
        FALLEN_WHITE,
        CELTIC_GUARDIAN,
        CELTIC_GUARDIAN,
        CELTIC_GUARDIAN,
        CELTIC_GUARDIAN,
        INCREDIBLE_ECCLESIA,
        GOLDEN_SWORDSOUL,
        GUIDING_QUEM,
        TRIBRIGADE_SPRINGANS_KITT,
        BLAZING_CARTESIA,
        DOGMATIKA_ECCLESIA,
        FALLEN_VIRTUOUS,
        MERCOURIER,
        BRANDED_RETRIBUTION,
        *filler,
    ]
    extra = [
        TITANIKLAD,
        ECCLESIA_DARK_DRAGON,
        THREE_CHAMPIONS,
        ALBION_BRANDED,
        MIRRORJADE,
        DEVOURS_DOGMA,
    ]
    opponent = ([ASH_BLOSSOM] + [CELTIC_GUARDIAN] * 39
                if opponent_ash else [CELTIC_GUARDIAN] * 40)
    duel = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    decision = duel.reset(deck, opponent, extra, seed=11)
    return duel, decision


def main():
    duel, decision = new_duel(ASH_MODE is not None)
    show("initial", decision, duel)
    decision = choose(duel, decision, "activate", FALLEN_WHITE)
    show("after Fallen hand effect", decision, duel)
    decision = choose(duel, decision, "select_card", TITANIKLAD)
    show("after sending Titaniklad", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "yes", FALLEN_WHITE)
    show("after accepting Fallen field trigger", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", INCREDIBLE_ECCLESIA)
    show("after selecting Incredible Ecclesia", decision, duel)
    decision = settle(duel, decision)
    show("Incredible Ecclesia summoned", decision, duel)
    decision = choose(duel, decision, "activate", INCREDIBLE_ECCLESIA)
    show("after activating Incredible Ecclesia", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", GOLDEN_SWORDSOUL)
    show("after selecting Golden Swordsoul", decision, duel)
    decision = settle(duel, decision)
    show("Golden Swordsoul summoned", decision, duel)
    decision = choose(duel, decision, "special_summon", ECCLESIA_DARK_DRAGON)
    show("after choosing Ecclesia and the Dark Dragon", decision, duel)
    decision = choose(duel, decision, "select_card", GOLDEN_SWORDSOUL)
    show("after selecting Golden Swordsoul as Synchro material", decision, duel)
    decision = choose(duel, decision, "select_sum", FALLEN_WHITE)
    show("after selecting Fallen as Synchro material", decision, duel)
    decision = settle(duel, decision)
    show("Ecclesia and the Dark Dragon summoned", decision, duel)
    decision = choose(duel, decision, "activate", ECCLESIA_DARK_DRAGON)
    show("after activating Ecclesia and the Dark Dragon", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", GUIDING_QUEM)
    show("after selecting Guiding Quem", decision, duel)
    decision = settle(duel, decision, stop_on_chain=True)
    show("Guiding Quem summoned", decision, duel)
    decision = choose(duel, decision, "chain", GUIDING_QUEM)
    show("after choosing Guiding Quem CL1", decision, duel)
    decision = choose(duel, decision, "chain", GOLDEN_SWORDSOUL)
    show("after choosing Golden Swordsoul CL2", decision, duel)
    decision = settle(duel, decision)
    show("resolving Quem and Golden chain", decision, duel)
    decision = choose(duel, decision, "select_card", INCREDIBLE_ECCLESIA)
    show("after selecting Incredible Ecclesia for CL2", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", TRIBRIGADE_SPRINGANS_KITT)
    show("after selecting Tri-Brigade Springans Kitt for CL1", decision, duel)
    decision = settle(duel, decision, stop_on_chain=True)
    show("Quem and Golden chain resolved", decision, duel)
    decision = choose(duel, decision, "yes", TRIBRIGADE_SPRINGANS_KITT)
    show("after accepting Kitt trigger", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", FALLEN_WHITE)
    show("after selecting Fallen for Kitt", decision, duel)
    decision = settle(duel, decision)
    show("Fallen summoned by Kitt", decision, duel)
    decision = choose(duel, decision, "special_summon", THREE_CHAMPIONS)
    show("after choosing Three Champions", decision, duel)
    decision = choose(duel, decision, "select_card", INCREDIBLE_ECCLESIA)
    show("after selecting Incredible Ecclesia as Synchro material", decision, duel)
    decision = choose(duel, decision, "select_sum", FALLEN_WHITE)
    show("after selecting Fallen as second Synchro material", decision, duel)
    decision = settle(duel, decision, stop_on_chain=True)
    show("Three Champions summoned", decision, duel)
    decision = choose(duel, decision, "chain", THREE_CHAMPIONS)
    show("after choosing Three Champions CL1", decision, duel)
    decision = choose(duel, decision, "chain", GUIDING_QUEM)
    show("after choosing Guiding Quem CL2", decision, duel)
    decision = choose(duel, decision, "select_card", FALLEN_WHITE)
    show("after targeting Fallen with Quem", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", BLAZING_CARTESIA)
    show("after selecting Blazing Cartesia for Three Champions", decision, duel)
    decision = settle(duel, decision)
    show("second trigger chain resolved", decision, duel)
    decision = choose(duel, decision, "activate", BLAZING_CARTESIA)
    show("after activating Cartesia in hand", decision, duel)
    decision = settle(duel, decision)
    show("Blazing Cartesia summoned", decision, duel)
    decision = choose(duel, decision, "activate", BLAZING_CARTESIA)
    show("after activating Cartesia Fusion effect", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", ALBION_BRANDED)
    show("after choosing Albion as Fusion summon", decision, duel)
    decision = choose(duel, decision, "select_toggle", FALLEN_WHITE)
    show("after selecting Fallen as Albion material", decision, duel)
    decision = choose(duel, decision, "select_toggle", THREE_CHAMPIONS)
    show("after selecting Three Champions as Albion material", decision, duel)
    decision = settle(duel, decision, stop_on_chain=True)
    show("Albion summoned", decision, duel)
    decision = choose(duel, decision, "yes", ALBION_BRANDED)
    show("after accepting Albion effect", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", MIRRORJADE)
    show("after choosing Mirrorjade", decision, duel)
    decision = choose(duel, decision, "select_toggle", FALLEN_WHITE)
    show("after selecting Fallen for Mirrorjade", decision, duel)
    decision = choose(duel, decision, "select_toggle", THREE_CHAMPIONS)
    show("after selecting Three Champions for Mirrorjade", decision, duel)
    decision = settle(duel, decision)
    show("Mirrorjade summoned", decision, duel)
    decision = choose(duel, decision, "end_phase")
    show("entered End Phase", decision, duel)
    decision = choose(duel, decision, "pass")
    show("after opponent End Phase pass", decision, duel)
    decision = choose(duel, decision, "chain", TITANIKLAD)
    show("after choosing Titaniklad End Phase effect", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", DOGMATIKA_ECCLESIA)
    show("after selecting Dogmatika Ecclesia", decision, duel)
    decision = settle(duel, decision, stop_on_chain=True)
    show("Dogmatika Ecclesia summoned", decision, duel)
    decision = choose(duel, decision, "option", description=1152)
    show("after choosing to Special Summon Dogmatika Ecclesia", decision, duel)
    decision = settle(duel, decision, stop_on_chain=True)
    show("Dogmatika Ecclesia Special Summoned", decision, duel)
    decision = choose(duel, decision, "yes", DOGMATIKA_ECCLESIA)
    show("after accepting Dogmatika Ecclesia effect", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", FALLEN_VIRTUOUS)
    show("after selecting The Fallen and The Virtuous", decision, duel)
    decision = settle(duel, decision, stop_on_chain=True)
    show("The Fallen and The Virtuous added", decision, duel)
    decision = choose(duel, decision, "chain", FALLEN_VIRTUOUS)
    show("after activating The Fallen and The Virtuous", decision, duel)
    decision = settle(duel, decision)
    show("The Fallen and The Virtuous placed", decision, duel)
    decision = choose(duel, decision, "option")
    show("after choosing destroy mode", decision, duel)
    decision = choose(duel, decision, "select_card", DEVOURS_DOGMA)
    show("after sending Devours the Dogma", decision, duel)
    decision = choose(duel, decision, "select_card", ALBION_BRANDED)
    show("after targeting Albion", decision, duel)
    decision = settle(duel, decision, stop_on_chain=True)
    show("The Fallen and The Virtuous resolved", decision, duel)
    decision = choose(duel, decision, "chain", DEVOURS_DOGMA)
    show("after choosing Devours the Dogma effect", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", MERCOURIER)
    show("after selecting Tri-Brigade Mercourier", decision, duel)
    decision = settle(duel, decision, stop_on_chain=True)
    show("Mercourier added", decision, duel)
    decision = choose(duel, decision, "chain", ALBION_BRANDED)
    show("after choosing Albion End Phase effect", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", BRANDED_RETRIBUTION)
    show("after selecting Branded Retribution", decision, duel)
    decision = choose(duel, decision, "option", description=1153)
    show("after choosing to Set Branded Retribution", decision, duel)
    decision = settle(duel, decision, stop_on_chain=True)
    show("Branded Retribution set", decision, duel)
    decision = choose(duel, decision, "chain", INCREDIBLE_ECCLESIA)
    show("after choosing Incredible Ecclesia End Phase effect", decision, duel)
    decision = settle(duel, decision)
    counts = duel.counts()
    assert decision["player"] == 1
    assert counts == {
        "deck0": 26, "hand0": 6, "monster0": 5, "spell_trap0": 1, "grave0": 5,
        "deck1": 34, "hand1": 6, "monster1": 0, "spell_trap1": 0, "grave1": 0,
    }
    show("FULL COMBO COMPLETE", decision, duel)
    if ASH_MODE is not None:
        print("FULL RESULT " + json.dumps({"prefix": action_prefix}))


if __name__ == "__main__":
    try:
        main()
    except LineInterrupted as interrupted:
        print("ASH RESULT " + json.dumps({
            "window": int(ASH_MODE),
            "label": ash_windows[int(ASH_MODE)],
            "expected": interrupted.expected,
            "prefix": action_prefix,
            "counts": interrupted.duel.counts(),
        }))
