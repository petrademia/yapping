"""Search the Albaz fixture from its opening decision against a known hand trap."""

import argparse

from analyze_ash import action_name, endboard_score, replay
from trace_albaz_combo import (
    ASH_BLOSSOM,
    CELTIC_GUARDIAN,
    DROLL_LOCK_BIRD,
    EFFECT_VEILER,
    GHOST_OGRE,
    INFINITE_IMPERMANENCE,
    NIBIRU,
)
from yapping import minimax_replay


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


def legal(snapshot):
    actions = snapshot.decision["actions"]
    seen = set()
    choices = []
    for index, action in enumerate(actions):
        if action["kind"] in SKIP_KINDS or action["card"] == CELTIC_GUARDIAN:
            continue
        signature = (action["kind"], action["card"], action["description"])
        if signature in seen:
            continue
        seen.add(signature)
        choices.append(index)
    if snapshot.decision["player"] == 1:
        return sorted(choices, key=lambda i: actions[i]["kind"] == "pass")
    return sorted(choices, key=lambda i: MAX_PRIORITY.get(actions[i]["kind"], 2))


def search(interruption="ash", max_nodes=10_000, max_depth=180, opening_hand=None):
    card = CARDS[interruption]
    result = minimax_replay(
        lambda path: replay(path, card, opening_hand),
        legal,
        endboard_score,
        lambda snapshot: snapshot.decision["turn"] >= 2,
        lambda snapshot: snapshot.decision["player"],
        max_depth=max_depth,
        max_nodes=max_nodes,
    )
    final = replay(result.actions, card, opening_hand)
    print(f"Opening-hand minimax against known {interruption}")
    if opening_hand is not None:
        print("opening hand: " + ", ".join(map(str, opening_hand)))
    print(f"score: {result.score:.2f}")
    print(f"visited states: {result.visited_states}")
    print(f"complete: {result.complete}")
    print("actions: " + " -> ".join(final.actions))
    print(f"end board: {final.zones}")
    return result, final


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("interruption", choices=CARDS, default="ash", nargs="?")
    parser.add_argument("--max-nodes", type=int, default=10_000)
    parser.add_argument("--max-depth", type=int, default=180)
    parser.add_argument("--hand", type=int, nargs=5, metavar="CARD_ID")
    arguments = parser.parse_args()
    search(arguments.interruption, arguments.max_nodes, arguments.max_depth, arguments.hand)
