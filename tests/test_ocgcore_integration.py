import sqlite3
from pathlib import Path

from yapping._ocgcore import Duel


POT_OF_GREED = 55144522
CELTIC_GUARDIAN = 91152256
SCRIPTS = Path(__file__).parents[2] / "fluorohydride-ygopro-scripts"


def make_database(path):
    database = sqlite3.connect(path)
    database.execute(
        """CREATE TABLE datas (
            id INTEGER PRIMARY KEY, ot INTEGER, alias INTEGER, setcode INTEGER,
            type INTEGER, atk INTEGER, def INTEGER, level INTEGER,
            race INTEGER, attribute INTEGER, category INTEGER
        )"""
    )
    database.executemany(
        "INSERT INTO datas VALUES (?, 0, 0, 0, ?, ?, ?, ?, ?, ?, 0)",
        [
            (POT_OF_GREED, 0x2, 0, 0, 0, 0, 0),
            (CELTIC_GUARDIAN, 0x11, 1400, 1200, 4, 0x1, 0x1),
        ],
    )
    database.commit()
    database.close()


def choose(duel, decision, kind, card=None):
    for index, action in enumerate(decision["actions"]):
        if action["kind"] == kind and (card is None or action["card"] == card):
            return duel.step(index)
    raise AssertionError(f"missing {kind} action for {card}: {decision['actions']}")


def resolve_prompts(duel, decision):
    while True:
        kinds = {action["kind"] for action in decision["actions"]}
        if "place" in kinds:
            decision = choose(duel, decision, "place")
        elif "pass" in kinds:
            decision = choose(duel, decision, "pass")
        else:
            break
    return decision


def test_real_spell_then_normal_summon(tmp_path):
    assert (SCRIPTS / "constant.lua").is_file()
    assert (SCRIPTS / f"c{POT_OF_GREED}.lua").is_file()
    database = tmp_path / "cards.cdb"
    make_database(database)

    deck = [POT_OF_GREED, CELTIC_GUARDIAN] * 20
    duel = Duel(str(database), str(SCRIPTS))
    decision = duel.reset(deck, deck, seed=7, start_hand=5)
    assert decision["player"] == 0
    assert {action["kind"] for action in decision["actions"]} >= {"activate", "summon"}
    assert 11 in decision["events"]  # MSG_SELECT_IDLECMD
    assert duel.counts()["hand0"] == 5
    assert duel.cards(0, 2).count(POT_OF_GREED) >= 2

    decision = choose(duel, decision, "activate", POT_OF_GREED)
    assert 18 in decision["events"]  # MSG_SELECT_PLACE
    assert any(action["kind"] == "place" for action in decision["actions"])
    decision = resolve_prompts(duel, decision)
    assert 90 in decision["events"]  # MSG_DRAW
    assert duel.counts()["hand0"] == 6
    assert duel.counts()["grave0"] == 1

    decision = choose(duel, decision, "summon", CELTIC_GUARDIAN)
    decision = resolve_prompts(duel, decision)
    assert 60 in decision["events"]  # MSG_SUMMONING
    assert 61 in decision["events"]  # MSG_SUMMONED
    assert duel.counts()["hand0"] == 5
    assert duel.counts()["monster0"] == 1
    assert duel.cards(0, 4) == [CELTIC_GUARDIAN]
