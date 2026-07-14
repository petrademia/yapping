"""Find Ash Blossom choke points and search legal post-negation continuations."""

import json
import os
import subprocess
import sys
from dataclasses import dataclass

from trace_albaz_combo import (
    ALBION_BRANDED,
    ASH_BLOSSOM,
    BLAZING_CARTESIA,
    BRANDED_RETRIBUTION,
    DOGMATIKA_ECCLESIA,
    ECCLESIA_DARK_DRAGON,
    FALLEN_VIRTUOUS,
    GUIDING_QUEM,
    INCREDIBLE_ECCLESIA,
    MERCOURIER,
    MIRRORJADE,
    ROOT,
    new_duel,
)
from yapping import opening_probability


HAND, MZONE, SZONE, GRAVE, REMOVED = 2, 4, 8, 16, 32
CARD_WEIGHTS = {
    MIRRORJADE: 10,
    BRANDED_RETRIBUTION: 5,
    GUIDING_QUEM: 4,
    BLAZING_CARTESIA: 3,
    DOGMATIKA_ECCLESIA: 2,
    ECCLESIA_DARK_DRAGON: 2,
    INCREDIBLE_ECCLESIA: 2,
    MERCOURIER: 2,
    FALLEN_VIRTUOUS: 2,
    ALBION_BRANDED: 1,
}


@dataclass(frozen=True)
class Snapshot:
    decision: dict
    counts: dict
    zones: dict
    key: bytes
    actions: tuple[str, ...]


@dataclass(frozen=True)
class Recovery:
    score: float
    suffix: tuple[int, ...]
    snapshot: Snapshot
    visited: int
    complete: bool


def interrupted_prefix(window, interruption="ash", target=0):
    environment = os.environ | {
        "YAPPING_INTERRUPTION": interruption,
        "YAPPING_WINDOW": str(window),
        "YAPPING_TARGET": str(target),
    }
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/trace_albaz_combo.py")],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"{interruption} window {window} target {target} trace failed:\n"
            + result.stderr[-2000:]
        )
    lines = result.stdout.splitlines()
    line = next(line for line in lines if line.startswith("INTERRUPTION RESULT ")
                or line.startswith("FULL RESULT "))
    value = json.loads(line.split(" ", 2)[2])
    value["completed"] = value.get("terminal", line.startswith("FULL RESULT "))
    return value


def uninterrupted_prefix(interruption="ash"):
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
    line = next(line for line in result.stdout.splitlines() if line.startswith("FULL RESULT "))
    return json.loads(line.removeprefix("FULL RESULT "))["prefix"]


def replay(indices, opponent_card=ASH_BLOSSOM, opening_hand=None):
    duel, decision = new_duel(opponent_card=opponent_card,
                              opponent_set=opponent_card == 24224830,
                              opening_hand=opening_hand)
    chosen = []
    for index in indices:
        action = decision["actions"][index]
        chosen.append(action_name(action))
        decision = duel.step(index)
    zones = {
        "hand": duel.cards(0, HAND),
        "monster": duel.cards(0, MZONE),
        "spell_trap": duel.cards(0, SZONE),
        "grave": duel.cards(0, GRAVE),
        "banished": duel.cards(0, REMOVED),
    }
    action_key = repr((decision["player"], decision["turn"], decision["actions"])).encode()
    return Snapshot(decision, duel.counts(), zones, bytes(duel.state_key()) + action_key,
                    tuple(chosen))


def action_name(action):
    card = action["card"]
    return f"{action['kind']}:{card}" if card else action["kind"]


def endboard_score(snapshot):
    zones = snapshot.zones
    score = snapshot.counts["hand0"] * 0.25
    score += sum(CARD_WEIGHTS.get(card, 0.5) for card in zones["monster"])
    score += sum(CARD_WEIGHTS.get(card, 0.5) for card in zones["spell_trap"])
    score += sum(CARD_WEIGHTS.get(card, 0) for card in zones["hand"])
    return score


def legal_indices(snapshot):
    actions = snapshot.decision["actions"]
    if snapshot.decision["player"] == 1:
        return tuple(i for i, action in enumerate(actions) if action["kind"] == "pass")
    # ponytail: equivalent copies/zones share one branch until positional scoring matters.
    seen = set()
    result = []
    for index, action in enumerate(actions):
        signature = (action["kind"], action["card"], action["description"])
        if action["kind"] in {"shuffle", "battle_phase"} or signature in seen:
            continue
        seen.add(signature)
        result.append(index)
    return tuple(result)


def search_recovery(prefix, opponent_card=ASH_BLOSSOM, max_depth=80, max_nodes=1500):
    frontier = [tuple()]
    seen = set()
    best = None
    while frontier and len(seen) < max_nodes:
        suffix = frontier.pop()
        snapshot = replay(tuple(prefix) + suffix, opponent_card)
        if snapshot.key in seen:
            continue
        seen.add(snapshot.key)
        terminal = snapshot.decision["turn"] >= 2
        if terminal:
            candidate = Recovery(endboard_score(snapshot), suffix, snapshot, len(seen), False)
            if best is None or candidate.score > best.score:
                best = candidate
            continue
        if len(suffix) < max_depth:
            frontier.extend(suffix + (index,) for index in legal_indices(snapshot))
    if best is None:
        snapshot = replay(prefix, opponent_card)
        best = Recovery(endboard_score(snapshot), tuple(), snapshot, len(seen), False)
    return Recovery(best.score, best.suffix, best.snapshot, len(seen), not frontier)


def analyze():
    rows = []
    for window in range(7):
        interruption = interrupted_prefix(window)
        recovery = search_recovery(interruption["prefix"])
        rows.append((interruption, recovery))

    print("Ash Blossom adversarial analysis")
    print("window  score  states  choke point")
    for interruption, recovery in rows:
        states = f"{recovery.visited}{'' if recovery.complete else '+'}"
        print(f"{interruption['window']:>6}  {recovery.score:>5.2f}  "
              f"{states:>6}  {interruption['label']}")
    worst, recovery = min(rows, key=lambda row: row[1].score)
    full_score = endboard_score(replay(uninterrupted_prefix()))
    ash_probability = opening_probability(40, 3, 5)
    expected_score = ((1 - ash_probability) * full_score
                      + ash_probability * recovery.score)
    print(f"\nBest Ash timing: window {worst['window']} — {worst['label']}")
    print(f"Best recovery score: {recovery.score:.2f}")
    actions = recovery.snapshot.actions[-len(recovery.suffix):] if recovery.suffix else ()
    print("Recovery actions: " + " -> ".join(actions))
    print("End board: " + json.dumps(recovery.snapshot.zones, sort_keys=True))
    print(f"\nOpen 3 Ash in 40 cards / 5-card hand: {ash_probability:.2%}")
    print(f"Uninterrupted score: {full_score:.2f}")
    print(f"Expected score versus Ash/no-Ash: {expected_score:.2f}")
    return rows


if __name__ == "__main__":
    analyze()
