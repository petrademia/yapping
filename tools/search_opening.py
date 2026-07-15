"""Search the Albaz fixture from its opening decision against a known hand trap."""

import argparse
import json

from analyze_ash import (CARD_WEIGHTS, ReplayCursor, action_name,
                          endboard_score, evaluation_context, replay,
                          score_breakdown)
from trace_albaz_combo import (
    ASH_BLOSSOM,
    CELTIC_GUARDIAN,
    DROLL_LOCK_BIRD,
    EFFECT_VEILER,
    GHOST_OGRE,
    INFINITE_IMPERMANENCE,
    NIBIRU,
    card_id,
    INCREDIBLE_ECCLESIA,
    ROOT,
    SCRIPTS,
)
from yapping import minimax_replay
from yapping._ocgcore import Duel
from matchup_config import load_config


# Cards that can legally interrupt the opponent's first turn from hand.
CARDS = {
    "ash": ASH_BLOSSOM,
    "veiler": EFFECT_VEILER,
    "impermanence": INFINITE_IMPERMANENCE,
    "droll": DROLL_LOCK_BIRD,
    "nibiru": NIBIRU,
    "ghost_ogre": GHOST_OGRE,
}
SKIP_KINDS = {"battle_phase", "shuffle"}
MAX_PRIORITY = {
    "activate": 0,
    "yes": 0,
    "chain": 0,
    "special_summon": 1,
    "select_card": 1,
    "select_sum": 1,
    "select_toggle": 1,
    "option": 1,
    "place": 2,
    "position": 2,
    "pass": 3,
    "end_phase": 4,
}


def legal(snapshot, config):
    actions = snapshot.decision["actions"]
    seen = set()
    choices = []
    for index, action in enumerate(actions):
        if action["kind"] in config["skip_kinds"] or action["card"] == CELTIC_GUARDIAN:
            continue
        signature = (action["kind"], action["card"], action["description"])
        if signature in seen:
            continue
        seen.add(signature)
        choices.append(index)
    if snapshot.decision["player"] == 1:
        return sorted(choices, key=lambda i: actions[i]["kind"] == "pass")
    # Alpha-beta reaches a useful lower bound sooner when high-value legal
    # continuations are examined first; every action remains searchable.
    return sorted(
        choices,
        key=lambda i: (config["move_priority"].get(actions[i]["kind"], 2),
                       -config["weights"].get(actions[i]["card"], 0), i),
    )


def recovery_terminal(snapshot, config):
    return (config["recovery_card"] in snapshot.zones["monster"]
            and any(action == "activate:73819701" for action in snapshot.actions))


def search(interruption="ash", max_nodes=10_000, max_depth=180, opening_hand=None,
           ecclesia_copies=1, recovery_only=False, config=None,
           replay_mode="cursor", adapter=None):
    config = config or load_config()
    card = config["interruptions"][interruption]
    adapter = adapter or Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    cursor = ReplayCursor(card, opening_hand, ecclesia_copies, adapter, config)
    replay_fn = cursor if replay_mode == "cursor" else lambda path: replay(
        path, card, opening_hand, ecclesia_copies, adapter, config)
    result = minimax_replay(
        replay_fn,
        lambda snapshot: legal(snapshot, config),
        lambda snapshot: endboard_score(snapshot, config["weights"]),
        (lambda snapshot: recovery_terminal(snapshot, config)) if recovery_only
        else lambda snapshot: snapshot.decision["turn"] >= 2,
        lambda snapshot: snapshot.decision["player"],
        max_depth=max_depth,
        max_nodes=max_nodes,
    )
    final = replay_fn(result.actions)
    print(f"Opening-hand minimax against known {interruption}")
    if opening_hand is not None:
        print("opening hand: " + ", ".join(map(str, opening_hand)))
    print(f"Ecclesia copies: {ecclesia_copies}")
    print(f"recovery-only: {recovery_only}")
    print(f"replay-mode: {replay_mode}")
    score_label = "score" if result.complete else "provisional score at search limit"
    print(f"{score_label}: {result.score:.2f}")
    print(f"visited states: {result.visited_states}")
    print(f"complete: {result.complete}")
    print("actions: " + " -> ".join(final.actions))
    print(f"end board: {final.zones}")
    print("score breakdown: " + json.dumps(score_breakdown(final, config["weights"]), sort_keys=True))
    print("evaluation context: " + json.dumps(evaluation_context(final), sort_keys=True))
    return result, final


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("interruption", choices=CARDS, default="ash", nargs="?")
    parser.add_argument("--max-nodes", type=int, default=10_000)
    parser.add_argument("--max-depth", type=int, default=180)
    parser.add_argument("--hand", type=card_id, nargs=5, metavar="CARD")
    parser.add_argument("--ecclesia-copies", type=int, default=1)
    parser.add_argument("--recovery-only", action="store_true")
    parser.add_argument("--config", type=str)
    parser.add_argument("--replay-mode", choices=["cursor", "oracle"], default="cursor")
    arguments = parser.parse_args()
    search(arguments.interruption, arguments.max_nodes, arguments.max_depth,
           arguments.hand, arguments.ecclesia_copies, arguments.recovery_only,
           load_config(arguments.config), arguments.replay_mode)
