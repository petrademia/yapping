import sqlite3
from pathlib import Path

import pytest

from yapping.ocg import (
    engine_paths,
    fluoro_assets_ready,
    ignis_assets_ready,
    make_duel,
)

REPO = Path(__file__).resolve().parents[1]

POT_OF_GREED = 55144522
CELTIC_GUARDIAN = 91152256


def _tiny_cdb(path):
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


def _choose(duel, decision, kind, card=None):
    for index, action in enumerate(decision["actions"]):
        if action["kind"] == kind and (card is None or action["card"] == card):
            return duel.step(index)
    raise AssertionError(f"missing {kind} {card}: {decision['actions']}")


def test_engine_paths_do_not_cross_stacks():
    fluoro_cdb, fluoro_scripts = engine_paths("fluoro")
    ignis_cdb, ignis_scripts = engine_paths("ignis")
    assert fluoro_cdb == REPO / "assets" / "cards.cdb"
    assert ignis_cdb == REPO / "assets" / "ignis" / "cards.cdb"
    assert fluoro_scripts.name == "fluorohydride-ygopro-scripts"
    assert ignis_scripts.name == "projectignis-card-scripts"
    assert fluoro_cdb != ignis_cdb
    assert fluoro_scripts != ignis_scripts


def test_make_duel_rejects_unknown_engine():
    with pytest.raises(ValueError, match="engine"):
        make_duel("edo")


@pytest.mark.skipif(not fluoro_assets_ready(), reason="Fluoro cdb/scripts missing")
def test_make_duel_fluoro_returns_existing_adapter():
    duel = make_duel("fluoro")
    assert type(duel).__module__ == "yapping._ocgcore"


@pytest.mark.skipif(not ignis_assets_ready(), reason="Ignis cdb/scripts missing")
def test_ignis_module_imports():
    from yapping._ocgcore_ignis import Duel
    cdb, scripts = engine_paths("ignis")
    duel = Duel(str(cdb), str(scripts))
    assert hasattr(duel, "reset")
    assert hasattr(duel, "step")
    assert hasattr(duel, "counts")
    assert hasattr(duel, "cards")
    assert hasattr(duel, "state_key")


@pytest.mark.skipif(not ignis_assets_ready(), reason="Ignis cdb/scripts missing")
def test_ignis_spell_then_normal_summon(tmp_path):
    from yapping._ocgcore_ignis import Duel

    _, scripts = engine_paths("ignis")
    assert (scripts / f"c{POT_OF_GREED}.lua").is_file() or (
        scripts / "official" / f"c{POT_OF_GREED}.lua"
    ).is_file()
    database = tmp_path / "cards.cdb"
    _tiny_cdb(database)
    deck = [POT_OF_GREED, CELTIC_GUARDIAN] * 20
    duel = Duel(str(database), str(scripts))
    decision = duel.reset(deck, deck, seed=7, start_hand=5)
    assert {action["kind"] for action in decision["actions"]} >= {"activate", "summon"}
    decision = _choose(duel, decision, "activate", POT_OF_GREED)
    while any(action["kind"] in {"place", "pass"} for action in decision["actions"]):
        kind = "place" if any(a["kind"] == "place" for a in decision["actions"]) else "pass"
        decision = _choose(duel, decision, kind)
    assert duel.counts()["grave0"] == 1
    decision = _choose(duel, decision, "summon", CELTIC_GUARDIAN)
    while any(action["kind"] == "place" for action in decision["actions"]):
        decision = _choose(duel, decision, "place")
    assert duel.cards(0, 4) == [CELTIC_GUARDIAN]


@pytest.mark.skipif(not ignis_assets_ready(), reason="Ignis cdb/scripts missing")
def test_ignis_reset_without_scripts_leaves_no_live_duel(tmp_path):
    from yapping._ocgcore_ignis import Duel

    database = tmp_path / "cards.cdb"
    _tiny_cdb(database)
    duel = Duel(str(database), str(tmp_path / "missing-scripts"))
    with pytest.raises(RuntimeError, match="constant.lua"):
        duel.reset([POT_OF_GREED] * 40, [POT_OF_GREED] * 40, seed=7)
    for query in (duel.counts, duel.state_key, lambda: duel.cards(0, 2)):
        with pytest.raises(RuntimeError, match="duel is not active"):
            query()


@pytest.mark.skipif(not ignis_assets_ready(), reason="Ignis cdb/scripts missing")
def test_ignis_reset_reports_starting_hand_and_state_key(tmp_path):
    from yapping._ocgcore_ignis import Duel

    _, scripts = engine_paths("ignis")
    database = tmp_path / "cards.cdb"
    _tiny_cdb(database)
    deck = [POT_OF_GREED, CELTIC_GUARDIAN] * 20
    duel = Duel(str(database), str(scripts))
    decision = duel.reset(deck, deck, seed=7, start_hand=5)
    assert decision["player"] == 0
    assert 11 in decision["events"]  # MSG_SELECT_IDLECMD
    counts = duel.counts()
    assert counts["hand0"] == 5
    assert counts["deck0"] == 35
    assert duel.cards(0, 2).count(POT_OF_GREED) >= 2
    assert isinstance(duel.state_key(), bytes)
    assert duel.state_key() == duel.state_key()
