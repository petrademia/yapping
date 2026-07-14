import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT.parent / "fluorohydride-ygopro-scripts"
CARDS = ROOT / "assets/cards.cdb"
sys.path.insert(0, str(ROOT / "tools"))
from trace_albaz_combo import (  # noqa: E402
    CELTIC_GUARDIAN,
    FALLEN_WHITE,
    INCREDIBLE_ECCLESIA,
    card_id,
    new_duel,
)


@pytest.mark.skipif(
    not CARDS.is_file() or not (SCRIPTS / "constant.lua").is_file(),
    reason="full card database and ygopro scripts are not installed",
)
def test_full_albaz_swordsoul_combo():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/trace_albaz_combo.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "FULL COMBO COMPLETE" in result.stdout


@pytest.mark.skipif(
    not CARDS.is_file() or not (SCRIPTS / "constant.lua").is_file(),
    reason="full card database and ygopro scripts are not installed",
)
def test_fixture_deals_requested_exact_opening_hand():
    hand = [FALLEN_WHITE, INCREDIBLE_ECCLESIA, CELTIC_GUARDIAN,
            CELTIC_GUARDIAN, CELTIC_GUARDIAN]
    duel, _ = new_duel(opening_hand=hand)
    assert sorted(duel.cards(0, 2)) == sorted(hand)


def test_fixture_card_aliases_resolve_for_command_line_hands():
    assert card_id("Fallen White") == FALLEN_WHITE
    assert card_id("incredible_ecclesia") == INCREDIBLE_ECCLESIA
    with pytest.raises(ValueError, match="unknown fixture card"):
        card_id("not_a_card")


@pytest.mark.skipif(
    not CARDS.is_file() or not (SCRIPTS / "constant.lua").is_file(),
    reason="full card database and ygopro scripts are not installed",
)
def test_ash_finds_choke_point_and_recovery():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/analyze_ash.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert sum("  after " in line for line in result.stdout.splitlines()) == 7
    assert "Best Ash timing: window 0" in result.stdout
    assert "Best recovery score: 8.75" in result.stdout
    assert "Recovery actions: end_phase" in result.stdout
    assert "select_card:45883110" in result.stdout  # Guiding Quem
    assert "select_card:95515789" in result.stdout  # Blazing Cartesia
    assert "score breakdown:" in result.stdout


@pytest.mark.skipif(
    not CARDS.is_file() or not (SCRIPTS / "constant.lua").is_file(),
    reason="full card database and ygopro scripts are not installed",
)
def test_opening_minimax_handles_known_veiler():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/search_opening.py"), "veiler"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "complete: True" in result.stdout
    assert "score: 8.75" in result.stdout
    assert "chain:97268402" in result.stdout


@pytest.mark.parametrize("interruption", ["veiler", "impermanence"])
@pytest.mark.skipif(
    not CARDS.is_file() or not (SCRIPTS / "constant.lua").is_file(),
    reason="full card database and ygopro scripts are not installed",
)
def test_monster_negation_targets_fallen(interruption):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/trace_albaz_combo.py")],
        cwd=ROOT,
        env=os.environ | {
            "YAPPING_INTERRUPTION": interruption,
            "YAPPING_WINDOW": "0",
        },
        capture_output=True,
        text=True,
        check=True,
    )
    assert '"targets": [73819701]' in result.stdout
    assert '"expected": "select_card 55273560"' in result.stdout


@pytest.mark.parametrize("interruption, window", [
    ("ghost_ogre", "0"), ("droll", "0"), ("nibiru", "9"), ("called_by", "0"),
])
@pytest.mark.skipif(
    not CARDS.is_file() or not (SCRIPTS / "constant.lua").is_file(),
    reason="full card database and ygopro scripts are not installed",
)
def test_additional_interruptions_have_legal_fixture(interruption, window):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/trace_albaz_combo.py")],
        cwd=ROOT,
        env=os.environ | {
            "YAPPING_INTERRUPTION": interruption,
            "YAPPING_WINDOW": window,
        },
        capture_output=True,
        text=True,
        check=True,
    )
    assert f"INTERRUPTION ACTIVATE {window}: {interruption}" in result.stdout
    assert "INTERRUPTION RESULT" in result.stdout
    if interruption == "nibiru":
        assert '"monster0": 1' in result.stdout  # Primal Being Token
        assert '"monster1": 1' in result.stdout  # Nibiru, the Primal Being
    if interruption == "called_by":
        assert '"targets": [41373230]' in result.stdout  # Titaniklad the Ash Dragon
        assert '"grave1": 1' in result.stdout  # Called by the Grave resolved from its Set zone
