"""Rank Effect Veiler and Infinite Impermanence timings and targets."""

import argparse
import json
import os
import subprocess
import sys

from analyze_ash import (
    Recovery,
    endboard_score,
    interrupted_prefix,
    replay,
    search_recovery,
    uninterrupted_prefix,
)
from trace_albaz_combo import (
    DROLL_LOCK_BIRD,
    CALLED_BY_THE_GRAVE,
    EFFECT_VEILER,
    GHOST_OGRE,
    INFINITE_IMPERMANENCE,
    NIBIRU,
    ROOT,
)
from yapping import opening_probability


CARDS = {
    "veiler": EFFECT_VEILER,
    "impermanence": INFINITE_IMPERMANENCE,
    "ghost_ogre": GHOST_OGRE,
    "droll": DROLL_LOCK_BIRD,
    "nibiru": NIBIRU,
    "called_by": CALLED_BY_THE_GRAVE,
}
NAMES = {
    41373230: "Titaniklad the Ash Dragon",
    73819701: "Fallen of the White Dragon",
    55273560: "Incredible Ecclesia",
    78397661: "Ecclesia and the Dark Dragon",
    45883110: "Guiding Quem",
    74405783: "Three Champions of Swordsoul",
    95515789: "Blazing Cartesia",
    87746184: "Albion the Branded Dragon",
    44146295: "Mirrorjade",
    60303688: "Dogmatika Ecclesia",
}
PRESET_INTERRUPTION = "called_by"


def windows(interruption):
    environment = os.environ | {
        "YAPPING_INTERRUPTION": interruption,
        "YAPPING_WINDOW": "hold",
    }
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/trace_albaz_combo.py")],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.split(": ", 1)[1] for line in result.stdout.splitlines()
            if line.startswith("INTERRUPTION WINDOW ")]


def outcome(interruption, result, max_nodes):
    card = CARDS[interruption]
    if result["completed"]:
        snapshot = replay(result["prefix"], card)
        return Recovery(endboard_score(snapshot), tuple(), snapshot, 1, True)
    return search_recovery(result["prefix"], card, max_nodes=max_nodes)


def analyze(interruption, max_nodes=1500, window=None):
    labels = windows(interruption)
    rows = []
    selected_windows = range(len(labels)) if window is None else (window,)
    for current_window in selected_windows:
        if current_window >= len(labels):
            raise ValueError(f"window {current_window} is outside 0..{len(labels) - 1}")
        label = labels[current_window]
        first = interrupted_prefix(current_window, interruption, 0)
        target_count = max(1, len(first["targets"]))
        results = [first]
        results.extend(interrupted_prefix(current_window, interruption, target)
                       for target in range(1, target_count))
        for target, result in enumerate(results):
            target_card = result["targets"][target] if result["targets"] else 0
            rows.append({
                "window": current_window,
                "label": label,
                "target": target_card,
                "recovery": outcome(interruption, result, max_nodes),
            })

    title = ("Called by the Grave pre-set backrow analysis"
             if interruption == PRESET_INTERRUPTION
             else f"{interruption.replace('_', ' ').title()} adversarial analysis")
    print(title)
    print("window  score  states  target                         timing")
    for row in rows:
        recovery = row["recovery"]
        target = NAMES.get(row["target"], str(row["target"]) if row["target"] else "-")
        states = f"{recovery.visited}{'' if recovery.complete else '+'}"
        print(f"{row['window']:>6}  {recovery.score:>5.2f}  {states:>6}  "
              f"{target:<29}  {row['label']}")

    worst = min(rows, key=lambda row: row["recovery"].score)
    recovery = worst["recovery"]
    full_score = endboard_score(replay(uninterrupted_prefix(interruption), CARDS[interruption]))
    target = NAMES.get(worst["target"], str(worst["target"]) if worst["target"] else "-")
    print(f"\nBest timing: window {worst['window']} — {worst['label']}")
    print(f"Best target: {target}")
    print(f"Best recovery score: {recovery.score:.2f}")
    actions = recovery.snapshot.actions[-len(recovery.suffix):] if recovery.suffix else ()
    print("Recovery actions: " + " -> ".join(actions))
    print("End board: " + json.dumps(recovery.snapshot.zones, sort_keys=True))
    if interruption == PRESET_INTERRUPTION:
        print("Scenario: Called by the Grave began Set before this turn; it is not a hand trap.")
    else:
        probability = opening_probability(40, 3, 5)
        expected = (1 - probability) * full_score + probability * recovery.score
        print(f"Expected score at 3 copies: {expected:.2f}")
    if any(not row["recovery"].complete for row in rows):
        print("States with + reached the recovery-search limit.")
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("interruption", choices=CARDS)
    parser.add_argument("--max-nodes", type=int, default=1500)
    parser.add_argument("--window", type=int)
    arguments = parser.parse_args()
    analyze(arguments.interruption, arguments.max_nodes, arguments.window)
