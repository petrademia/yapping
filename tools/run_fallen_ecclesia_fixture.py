"""Run the two-card Fallen + Ecclesia fixture and its recovery branches."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCENARIOS = (None, "ash", "veiler", "impermanence")


def run(interruption):
    env = os.environ | {
        "YAPPING_CONFIG": "configs/branded_albaz_v1.json",
        "YAPPING_TWO_CARD": "1",
    }
    if interruption:
        env.update({"YAPPING_INTERRUPTION": interruption, "YAPPING_WINDOW": "0"})
    else:
        env.pop("YAPPING_INTERRUPTION", None)
        env.pop("YAPPING_WINDOW", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/trace_albaz_combo.py")],
        cwd=ROOT, env=env, capture_output=True, text=True, check=True,
    )
    match = re.search(r"FULL COMBO COMPLETE: player=(\d+) counts=(\{.*\})", result.stdout)
    return {
        "interruption": interruption,
        "complete": match is not None,
        "recovery_normal_summon": "TWO_CARD RECOVERY: normal summon Incredible Ecclesia" in result.stdout,
        "expected_endboard": [24915933, 45883110, 73819701, 55273560, 17751597],
        "counts": match.group(2) if match else None,
    }


if __name__ == "__main__":
    print(json.dumps({"scenarios": [run(scenario) for scenario in SCENARIOS]},
                     indent=2, sort_keys=True))
