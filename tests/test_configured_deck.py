"""Native/integration checks for configured-deck opening-hand construction."""

from pathlib import Path

import pytest

from matchup_config import experiment_matchup, load_config
from yapping.hands import sample_unique_hands, validate_hand_in_deck

ROOT = Path(__file__).parents[1]
CARDS = ROOT / "assets/cards.cdb"
SCRIPTS = ROOT.parent / "fluorohydride-ygopro-scripts"


@pytest.mark.skipif(
    not CARDS.is_file() or not (SCRIPTS / "constant.lua").is_file(),
    reason="full card database and ygopro scripts are not installed",
)
def test_branded_config_accepts_hands_sampled_from_its_deck():
    from analyze_ash import replay
    from yapping._ocgcore import Duel

    config = load_config(ROOT / "configs/branded_albaz_v1.json")
    hand = next(sample_unique_hands(config["main_deck"], 1, seed=7))
    validate_hand_in_deck(config["main_deck"], hand)
    matchup = experiment_matchup(config, opening_hand=hand)
    assert matchup is config
    adapter = Duel(str(CARDS), str(SCRIPTS))
    try:
        snapshot = replay((), None, list(hand), adapter=adapter, matchup=matchup)
        assert sorted(snapshot.zones["hand"]) == sorted(hand)
    finally:
        del adapter


@pytest.mark.skipif(
    not CARDS.is_file() or not (SCRIPTS / "constant.lua").is_file(),
    reason="full card database and ygopro scripts are not installed",
)
def test_branded_hand_still_fails_against_fixture_deck():
    from analyze_ash import replay
    from yapping._ocgcore import Duel

    config = load_config(ROOT / "configs/branded_albaz_v1.json")
    # Prefer a hand that includes a branded-only card when possible.
    hand = None
    for candidate in sample_unique_hands(config["main_deck"], 40, seed=11):
        if 44362883 in candidate or 95515789 in candidate:
            hand = candidate
            break
    assert hand is not None
    adapter = Duel(str(CARDS), str(SCRIPTS))
    try:
        with pytest.raises(ValueError, match="not in this deck"):
            replay((), None, list(hand), adapter=adapter, matchup=None)
    finally:
        del adapter


@pytest.mark.skipif(
    not CARDS.is_file() or not (SCRIPTS / "constant.lua").is_file(),
    reason="full card database and ygopro scripts are not installed",
)
def test_default_fixture_search_path_still_constructs_without_opening_hand():
    from analyze_ash import replay
    from yapping._ocgcore import Duel

    config = load_config(ROOT / "configs/albaz.json")
    assert experiment_matchup(config, opening_hand=None) is None
    adapter = Duel(str(CARDS), str(SCRIPTS))
    try:
        snapshot = replay((), None, None, adapter=adapter, matchup=None)
        assert len(snapshot.zones["hand"]) == 5
    finally:
        del adapter
