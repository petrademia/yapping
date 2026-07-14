import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT.parent / "fluorohydride-ygopro-scripts"
CARDS = ROOT / "assets/cards.cdb"


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
