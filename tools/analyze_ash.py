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
    fixture_deck,
)
from yapping import EndboardEvaluator, EvaluationState, opening_probability
from matchup_config import load_config


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


class ReplayCursor:
    """Reuse forward descent; reconstruct only after backtracking."""

    def __init__(self, opponent_card=ASH_BLOSSOM, opening_hand=None,
                 ecclesia_copies=1, adapter=None, matchup=None):
        self.opponent_card = opponent_card
        self.opening_hand = opening_hand
        self.ecclesia_copies = ecclesia_copies
        self.adapter = adapter
        self.matchup = matchup
        self.path = ()
        self.snapshot = replay((), opponent_card, opening_hand,
                               ecclesia_copies, adapter, matchup)

    def __call__(self, path):
        if not (len(path) >= len(self.path) and
                path[:len(self.path)] == self.path):
            self.snapshot = replay((), self.opponent_card, self.opening_hand,
                                   self.ecclesia_copies, self.adapter, self.matchup)
            self.path = ()
        if path != self.path:
            chosen = list(self.snapshot.actions)
            decision = self.snapshot.decision
            for index in path[len(self.path):]:
                action = decision["actions"][index]
                chosen.append(action_name(action))
                decision = self.adapter.step(index)
            self.snapshot = snapshot_from_duel(self.adapter, decision,
                                               tuple(chosen))
            self.path = path
        return self.snapshot


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


def replay(indices, opponent_card=ASH_BLOSSOM, opening_hand=None,
           ecclesia_copies=1, adapter=None, matchup=None):
    main_deck = list(matchup["main_deck"]) if matchup else fixture_deck()
    if ecclesia_copies > 1:
        main_deck[1:1 + ecclesia_copies - 1] = [INCREDIBLE_ECCLESIA] * (ecclesia_copies - 1)
    duel, decision = new_duel(opponent_card=opponent_card,
                              opponent_set=opponent_card == 24224830,
                              opening_hand=opening_hand,
                              main_deck=main_deck,
                              extra_deck=matchup.get("extra_deck") if matchup else None,
                              adapter=adapter)
    chosen = []
    for index in indices:
        action = decision["actions"][index]
        chosen.append(action_name(action))
        decision = duel.step(index)
    return snapshot_from_duel(duel, decision, tuple(chosen))


def snapshot_from_duel(duel, decision, chosen):
    zones = {
        "hand": duel.cards(0, HAND),
        "monster": duel.cards(0, MZONE),
        "spell_trap": duel.cards(0, SZONE),
        "grave": duel.cards(0, GRAVE),
        "banished": duel.cards(0, REMOVED),
    }
    action_key = repr((decision["player"], decision["turn"], decision["actions"])).encode()
    return Snapshot(decision, duel.counts(), zones, bytes(duel.state_key()) + action_key,
                    chosen)


def action_name(action):
    card = action["card"]
    return f"{action['kind']}:{card}" if card else action["kind"]


def endboard_score(snapshot, weights=None, config=None):
    return sum(score_breakdown(snapshot, weights, config).values())


def evaluation_context(snapshot, weights=None, config=None):
    """Expose state facts for future calibrated card/location scoring."""
    actions = snapshot.decision["actions"]
    activated = {action["card"] for action in actions
                 if action["kind"] in {"activate", "chain"}}
    config = config or {}
    searchable_weights = weights if weights is not None else config.get("weights", CARD_WEIGHTS)
    return {
        "normal_summon_available": any(action["kind"] == "summon"
                                       for action in actions),
        "legal_activations": [action["card"] for action in actions
                               if action["kind"] in {"activate", "chain"}],
        "effects_used_in_line": sorted(activated),
        "opponent_interrupted": any(action.startswith("chain:")
                                     for action in snapshot.actions),
        "searchable_or_recoverable": [card for card in snapshot.zones["hand"]
                                       if card in searchable_weights],
    }


def score_breakdown(snapshot, weights=None, config=None):
    config = config or {}
    weights = config.get("weights", CARD_WEIGHTS) if weights is None else weights
    evaluator = EndboardEvaluator(weights)
    state = EvaluationState(snapshot.zones, evaluation_context(snapshot, weights, config))
    return evaluator.breakdown(state)


def score_categories(snapshot, weights=None, config=None):
    config = config or {}
    weights = config.get("weights", CARD_WEIGHTS) if weights is None else weights
    evaluator = EndboardEvaluator(weights)
    state = EvaluationState(snapshot.zones, evaluation_context(snapshot, weights, config))
    return evaluator.categories(state)


def legal_indices(snapshot, config=None):
    config = config or {}
    skip_kinds = set(config.get("skip_kinds", ("shuffle", "battle_phase")))
    actions = snapshot.decision["actions"]
    if snapshot.decision["player"] == 1:
        return tuple(i for i, action in enumerate(actions) if action["kind"] == "pass")
    # ponytail: equivalent copies/zones share one branch until positional scoring matters.
    seen = set()
    result = []
    for index, action in enumerate(actions):
        signature = (action["kind"], action["card"], action["description"])
        if action["kind"] in skip_kinds or signature in seen:
            continue
        seen.add(signature)
        result.append(index)
    return tuple(result)


def search_recovery(prefix, opponent_card=ASH_BLOSSOM, max_depth=80,
                    max_nodes=1500, config=None):
    frontier = [tuple()]
    seen = set()
    best = None
    while frontier and len(seen) < max_nodes:
        suffix = frontier.pop()
        snapshot = replay(tuple(prefix) + suffix, opponent_card, matchup=config)
        if snapshot.key in seen:
            continue
        seen.add(snapshot.key)
        terminal = (config or {}).get("terminal_turn", 2) <= snapshot.decision["turn"]
        if terminal:
            candidate = Recovery(endboard_score(snapshot, config=config), suffix, snapshot, len(seen), False)
            if best is None or candidate.score > best.score:
                best = candidate
            continue
        if len(suffix) < max_depth:
            frontier.extend(suffix + (index,) for index in legal_indices(snapshot, config))
    if best is None:
        snapshot = replay(prefix, opponent_card, matchup=config)
        best = Recovery(endboard_score(snapshot, config=config), tuple(), snapshot, len(seen), False)
    return Recovery(best.score, best.suffix, best.snapshot, len(seen), not frontier)


def analyze():
    config = load_config()
    rows = []
    for window in range(7):
        interruption = interrupted_prefix(window)
        recovery = search_recovery(interruption["prefix"], config=config)
        rows.append((interruption, recovery))

    print("Ash Blossom adversarial analysis")
    print("window  score  states  choke point")
    for interruption, recovery in rows:
        states = f"{recovery.visited}{'' if recovery.complete else '+'}"
        print(f"{interruption['window']:>6}  {recovery.score:>5.2f}  "
              f"{states:>6}  {interruption['label']}")
    worst, recovery = min(rows, key=lambda row: row[1].score)
    full_score = endboard_score(replay(uninterrupted_prefix(), matchup=config), config=config)
    ash_probability = opening_probability(40, 3, 5)
    expected_score = ((1 - ash_probability) * full_score
                      + ash_probability * recovery.score)
    print(f"\nBest Ash timing: window {worst['window']} — {worst['label']}")
    print(f"Best recovery score: {recovery.score:.2f}")
    actions = recovery.snapshot.actions[-len(recovery.suffix):] if recovery.suffix else ()
    print("Recovery actions: " + " -> ".join(actions))
    print("End board: " + json.dumps(recovery.snapshot.zones, sort_keys=True))
    print("score breakdown: " + json.dumps(score_breakdown(recovery.snapshot, config=config), sort_keys=True))
    print(f"\nOpen 3 Ash in 40 cards / 5-card hand: {ash_probability:.2%}")
    print(f"Uninterrupted score: {full_score:.2f}")
    print(f"Expected score versus Ash/no-Ash: {expected_score:.2f}")
    return rows


if __name__ == "__main__":
    analyze()
