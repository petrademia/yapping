import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
CARDS = ROOT / "assets/cards.cdb"
SCRIPTS = ROOT.parent / "fluorohydride-ygopro-scripts"

@pytest.mark.skipif(
    not CARDS.is_file() or not (SCRIPTS / "constant.lua").is_file(),
    reason="full card database and ygopro scripts are not installed",
)
def test_high_spirits_spellcaster_activation_is_legal():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/trace_high_spirits.py")],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert "HIGH SPIRITS TARGETS" in result.stdout
    assert "Granguignol the Dusk Dragon" in result.stdout
    assert "HIGH SPIRITS FALLEN LINE VALIDATED" in result.stdout
    assert "ECCLESIA TARGET VALIDATED" in result.stdout
    assert "GOLDEN SWORDSOUL TARGET VALIDATED" in result.stdout
    assert "ECCLESIA DARK SYNCHRO VALIDATED" in result.stdout
    assert "ECCLESIA DARK SUMMONED" in result.stdout
    assert "ECCLESIA DARK EFFECT VALIDATED" in result.stdout
    assert "QUEM SUMMON VALIDATED" in result.stdout
    assert "QUEM EFFECT VALIDATED" in result.stdout
    assert "QUEM SENDS KITT VALIDATED" in result.stdout
    assert "KITT REVIVES FALLEN VALIDATED" in result.stdout
    assert "THREE CHAMPIONS SYNCHRO VALIDATED" in result.stdout
    assert "THREE CHAMPIONS SUMMONED" in result.stdout
    assert "THREE CHAMPIONS ADDS CARTESIA" in result.stdout
