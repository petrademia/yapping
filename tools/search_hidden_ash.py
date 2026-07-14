"""Choose an opening action without revealing whether the opponent holds a hand trap."""

import argparse

from analyze_ash import endboard_score, replay
from search_opening import CARDS, legal
from trace_albaz_combo import card_id
from yapping import hidden_minimax_replay


def key(snapshot, index):
    action = snapshot.decision["actions"][index]
    return tuple(action[field] for field in (
        "kind", "card", "controller", "location", "sequence", "description",
    ))


def search(interruption="ash", max_nodes=10_000, max_depth=180, opening_hand=None):
    cards = {interruption: CARDS[interruption], "none": None}
    result = hidden_minimax_replay(
        lambda scenario, path: replay(path, cards[scenario], opening_hand),
        legal,
        key,
        endboard_score,
        lambda snapshot: snapshot.decision["turn"] >= 2,
        lambda snapshot: snapshot.decision["player"],
        tuple(cards),
        max_nodes=max_nodes,
        max_depth=max_depth,
    )
    print(f"Opening-hand maximin against hidden {interruption}")
    if opening_hand is not None:
        print("opening hand: " + ", ".join(map(str, opening_hand)))
    print(f"common first action: {result.action}")
    print(f"worst-case score: {result.score:.2f}")
    print(f"visited states: {result.visited_states}")
    print(f"complete: {result.complete}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("interruption", choices=CARDS, default="ash", nargs="?")
    parser.add_argument("--max-nodes", type=int, default=10_000)
    parser.add_argument("--max-depth", type=int, default=180)
    parser.add_argument("--hand", type=card_id, nargs=5, metavar="CARD")
    arguments = parser.parse_args()
    search(arguments.interruption, arguments.max_nodes, arguments.max_depth, arguments.hand)
