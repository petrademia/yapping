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
def test_mdm_one_card_fallen_reaches_end_phase_branch():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/trace_mdm_one_card.py")],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert "AFTER GRANGUIGNOL" in result.stdout
    assert "AFTER DEVOURS SEND" in result.stdout
    assert "FALLEN VIRTUOUS ADDED" in result.stdout
    assert "CARTESIA RETURN VALIDATED" in result.stdout
    assert "MDM ONE CARD PARTIAL VALIDATED" in result.stdout
