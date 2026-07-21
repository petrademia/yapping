"""Run the Aluber fixture against every configured interruption."""

import json
import os
import subprocess
import sys
from pathlib import Path
from yapping import report_provenance


ROOT = Path(__file__).parents[1]
INTERRUPTIONS = ("ash", "veiler", "impermanence", "droll", "nibiru", "ghost_ogre")


def main():
    reports = []
    for interruption in INTERRUPTIONS:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/trace_aluber_combo.py")],
            cwd=ROOT, env=os.environ | {"YAPPING_ALUBER_INTERRUPTION": interruption},
            capture_output=True, text=True, check=True,
        )
        reports.append(json.loads(result.stdout))
    print(json.dumps({
        "provenance": report_provenance(
            database=ROOT / "assets/cards.cdb",
            scripts=ROOT.parent / "fluorohydride-ygopro-scripts",
            max_nodes=None, max_depth=None,
            complete=all(row["complete"] for row in reports),
            revision_root=ROOT,
        ),
        "scenarios": reports,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
