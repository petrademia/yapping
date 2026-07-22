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
EFFECT_VEILER = 97268402
INFINITE_IMPERMANENCE = 10045474
GHOST_OGRE = 59438930
DROLL_LOCK_BIRD = 94145021
NIBIRU = 27204311
CALLED_BY_THE_GRAVE = 24224830
ALUBER = 62962630
BRANDED_FUSION = 44362883
GRANGUIGNOL = 24915933

CARD_IDS = {
    "fallen": FALLEN_WHITE,
    "fallen_white": FALLEN_WHITE,
    "titaniklad": TITANIKLAD,
    "incredible_ecclesia": INCREDIBLE_ECCLESIA,
    "golden_swordsoul": GOLDEN_SWORDSOUL,
    "ecclesia_dark": ECCLESIA_DARK_DRAGON,
    "guiding_quem": GUIDING_QUEM,
    "kitt": TRIBRIGADE_SPRINGANS_KITT,
    "three_champions": THREE_CHAMPIONS,
    "cartesia": BLAZING_CARTESIA,
    "albion": ALBION_BRANDED,
    "mirrorjade": MIRRORJADE,
    "dogmatika_ecclesia": DOGMATIKA_ECCLESIA,
    "fallen_virtuous": FALLEN_VIRTUOUS,
    "mercourier": MERCOURIER,
    "branded_retribution": BRANDED_RETRIBUTION,
    "celtic_guardian": CELTIC_GUARDIAN,
    "aluber": ALUBER,
    "aluber_the_jester": ALUBER,
    "branded_fusion": BRANDED_FUSION,
    "granguignol": GRANGUIGNOL,
}


def card_id(value):
    """Resolve a fixture card alias or numeric card ID for command-line hands."""
    normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in CARD_IDS:
        return CARD_IDS[normalized]
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"unknown fixture card: {value}") from error

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT.parent / "fluorohydride-ygopro-scripts"
INTERRUPTIONS = {
    "ash": ASH_BLOSSOM,
    "veiler": EFFECT_VEILER,
    "impermanence": INFINITE_IMPERMANENCE,
    "ghost_ogre": GHOST_OGRE,
    "droll": DROLL_LOCK_BIRD,
    "nibiru": NIBIRU,
    "called_by": CALLED_BY_THE_GRAVE,
}
INTERRUPTION = os.getenv("YAPPING_INTERRUPTION")
MODE = os.getenv("YAPPING_WINDOW")
TWO_CARD = bool(os.getenv("YAPPING_TWO_CARD"))
if os.getenv("YAPPING_ASH") is not None:  # Backward-compatible report/test entrypoint.
    INTERRUPTION, MODE = "ash", os.environ["YAPPING_ASH"]
if INTERRUPTION is not None and INTERRUPTION not in INTERRUPTIONS:
    raise ValueError(f"unknown interruption: {INTERRUPTION}")
interruption_windows = []
current_label = "initial"
action_prefix = []
interruption_activated = False
two_card_recovery = False
interruption_targets = []


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
    if label not in {"after pass", "after place", "after position"}:
        current_label = label
    print(f"\n{label}: player={decision['player']} counts={duel.counts()}")
    for index, action in enumerate(decision["actions"]):
        print(index, action)


def answer_interruption(duel, decision):
    global interruption_activated
    actions = decision["actions"]
    if decision["player"] != 1 or INTERRUPTION is None:
        return None
    card = INTERRUPTIONS[INTERRUPTION]
    activation = next((i for i, action in enumerate(actions)
                       if action["kind"] == "chain" and action["card"] == card), None)
    if activation is not None and not interruption_activated:
        window = len(interruption_windows)
        interruption_windows.append(current_label)
        print(f"INTERRUPTION WINDOW {window}: {current_label}")
        if MODE == str(window):
            print(f"INTERRUPTION ACTIVATE {window}: {INTERRUPTION}")
            interruption_activated = True
            return step(duel, activation)
        return step(duel, next(i for i, action in enumerate(actions)
                               if action["kind"] == "pass"))
    if interruption_activated:
        selectable = [i for i, action in enumerate(actions)
                      if action["kind"] == "select_card"]
        if selectable:
            interruption_targets.extend(actions[i]["card"] for i in selectable)
            target = min(int(os.getenv("YAPPING_TARGET", 0)), len(selectable) - 1)
            return step(duel, selectable[target])
        for kind in ("place", "position", "pass"):
            response = next((i for i, action in enumerate(actions)
                             if action["kind"] == kind), None)
            if response is not None:
                return step(duel, response)
    return None


def choose(duel, decision, kind, card=None, description=None):
    while True:
        for index, action in enumerate(decision["actions"]):
            if (action["kind"] == kind
                    and (card is None or action["card"] == card)
                    and (description is None or action["description"] == description)):
                return step(duel, index)
        answered = answer_interruption(duel, decision)
        if answered is None:
            break
        decision = answered
    if interruption_activated:
        if TWO_CARD and kind == "select_card" and card == INCREDIBLE_ECCLESIA:
            summon = next((i for i, candidate in enumerate(decision["actions"])
                           if candidate["kind"] == "summon"
                           and candidate["card"] == INCREDIBLE_ECCLESIA), None)
            if summon is not None:
                global two_card_recovery
                two_card_recovery = True
                print("TWO_CARD RECOVERY: normal summon Incredible Ecclesia")
                return step(duel, summon)
        raise LineInterrupted(duel, decision, f"{kind} {card}")
    raise RuntimeError(f"missing {kind} {card}")


def settle(duel, decision, stop_on_chain=False):
    while True:
        answered = answer_interruption(duel, decision)
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


def fixture_deck():
    filler = [CELTIC_GUARDIAN] * 26
    return [
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


def new_duel(opponent_ash=False, opponent_card=None, opponent_set=False,
             opening_hand=None, main_deck=None, extra_deck=None,
             opponent_deck=None, adapter=None, controlled_player=0):
    deck = list(fixture_deck() if main_deck is None else main_deck)
    if len(deck) < 40:
        raise ValueError("main_deck must contain at least 40 cards")
    if opening_hand is not None:
        if len(opening_hand) != 5:
            raise ValueError("opening_hand must contain exactly five cards")
        remaining = list(deck)
        for card in opening_hand:
            try:
                remaining.remove(card)
            except ValueError as error:
                raise ValueError(f"opening hand card {card} is not in this deck") from error
        deck = [*opening_hand, *remaining]
    extra = extra_deck or [
        TITANIKLAD,
        ECCLESIA_DARK_DRAGON,
        THREE_CHAMPIONS,
        ALBION_BRANDED,
        MIRRORJADE,
        DEVOURS_DOGMA,
    ]
    opponent_card = opponent_card or (ASH_BLOSSOM if opponent_ash else None)
    filler = list(opponent_deck or [CELTIC_GUARDIAN] * 40)
    opponent = ([opponent_card] + filler[1:]
                if opponent_card and not opponent_set else filler)
    duel = adapter or Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    if controlled_player not in (0, 1):
        raise ValueError("controlled_player must be 0 or 1")
    if controlled_player == 0:
        decision = duel.reset(deck, opponent, extra, seed=11,
                              set1=[opponent_card] if opponent_set and opponent_card else [])
    else:
        decision = duel.reset(opponent, deck, [], extra, seed=11,
                              set0=[opponent_card] if opponent_set and opponent_card else [])
    return duel, decision


def main():
    main_deck = None
    extra_deck = None
    opening_hand = None
    config_path = os.getenv("YAPPING_CONFIG")
    if config_path:
        config = json.loads(Path(config_path).read_text())
        main_deck = config["main_deck"]
        extra_deck = config["extra_deck"]
    if os.getenv("YAPPING_TWO_CARD"):
        opening_hand = [
            FALLEN_WHITE, INCREDIBLE_ECCLESIA,
            ASH_BLOSSOM, ASH_BLOSSOM, GHOST_OGRE,
        ]
    duel, decision = new_duel(
        opponent_card=INTERRUPTIONS.get(INTERRUPTION),
        opponent_set=INTERRUPTION == "called_by",
        opening_hand=opening_hand, main_deck=main_deck, extra_deck=extra_deck,
    )
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
    while not any(candidate["kind"] == "chain" and candidate["card"] == DEVOURS_DOGMA
                  for candidate in decision["actions"]):
        if any(candidate["kind"] == "pass" for candidate in decision["actions"]):
            decision = choose(duel, decision, "pass")
        else:
            raise RuntimeError(f"Dogma trigger window not reached: {decision['actions']}")
    decision = choose(duel, decision, "chain", DEVOURS_DOGMA)
    show("after choosing Devours the Dogma effect", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", MERCOURIER)
    show("after selecting Tri-Brigade Mercourier", decision, duel)
    decision = settle(duel, decision, stop_on_chain=True)
    show("Mercourier added", decision, duel)
    while not any(candidate["kind"] == "chain" and candidate["card"] == ALBION_BRANDED
                  for candidate in decision["actions"]):
        if any(candidate["kind"] == "pass" for candidate in decision["actions"]):
            decision = choose(duel, decision, "pass")
        else:
            raise RuntimeError(f"Albion end-phase trigger window not reached: {decision['actions']}")
    decision = choose(duel, decision, "chain", ALBION_BRANDED)
    show("after choosing Albion End Phase effect", decision, duel)
    decision = settle(duel, decision)
    decision = choose(duel, decision, "select_card", BRANDED_RETRIBUTION)
    show("after selecting Branded Retribution", decision, duel)
    decision = choose(duel, decision, "option", description=1153)
    show("after choosing to Set Branded Retribution", decision, duel)
    decision = settle(duel, decision, stop_on_chain=True)
    show("Branded Retribution set", decision, duel)
    while not any(candidate["kind"] == "chain" and candidate["card"] == INCREDIBLE_ECCLESIA
                  for candidate in decision["actions"]):
        if any(candidate["kind"] == "pass" for candidate in decision["actions"]):
            decision = choose(duel, decision, "pass")
        else:
            raise RuntimeError(f"Ecclesia End Phase window not reached: {decision['actions']}")
    decision = choose(duel, decision, "chain", INCREDIBLE_ECCLESIA)
    show("after choosing Incredible Ecclesia End Phase effect", decision, duel)
    decision = settle(duel, decision)
    counts = duel.counts()
    if not interruption_activated and not config_path:
        assert decision["player"] == 1
        assert {key: counts[key] for key in (
            "deck0", "hand0", "monster0", "spell_trap0", "grave0"
        )} == {
            "deck0": 26, "hand0": 6, "monster0": 5,
            "spell_trap0": 1, "grave0": 5,
        }
    show("FULL COMBO COMPLETE", decision, duel)
    if INTERRUPTION is not None:
        print("FULL RESULT " + json.dumps({
            "interruption": INTERRUPTION,
            "window": int(MODE) if MODE and MODE.isdigit() else None,
            "label": (interruption_windows[int(MODE)]
                      if MODE and MODE.isdigit() else None),
            "prefix": action_prefix,
            "targets": interruption_targets,
            "terminal": decision["turn"] >= 2,
        }))


if __name__ == "__main__":
    try:
        main()
    except LineInterrupted as interrupted:
        print("INTERRUPTION RESULT " + json.dumps({
            "interruption": INTERRUPTION,
            "window": int(MODE),
            "label": interruption_windows[int(MODE)],
            "expected": interrupted.expected,
            "prefix": action_prefix,
            "counts": interrupted.duel.counts(),
            "targets": interruption_targets,
        }))
