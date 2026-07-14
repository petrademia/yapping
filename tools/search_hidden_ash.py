"""Choose an opening action without revealing whether the opponent holds Ash."""

import argparse

from analyze_ash import endboard_score, replay
from search_opening import legal
from trace_albaz_combo import ASH_BLOSSOM
from yapping import hidden_minimax_replay


def key(snapshot, index):
    action = snapshot.decision["actions"][index]
    return tuple(action[field] for field in (
        "kind", "card", "controller", "location", "sequence", "description",
    ))


def search(max_nodes=10_000, max_depth=180):
    cards = {"ash": ASH_BLOSSOM, "no_ash": None}
    result = hidden_minimax_replay(
        lambda scenario, path: replay(path, cards[scenario]),
        legal,
        key,
        endboard_score,
        lambda snapshot: snapshot.decision["turn"] >= 2,
        lambda snapshot: snapshot.decision["player"],
        tuple(cards),
        max_nodes=max_nodes,
        max_depth=max_depth,
    )
    print("Opening-hand maximin against hidden Ash")
    print(f"common first action: {result.action}")
    print(f"worst-case score: {result.score:.2f}")
    print(f"visited states: {result.visited_states}")
    print(f"complete: {result.complete}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-nodes", type=int, default=10_000)
    parser.add_argument("--max-depth", type=int, default=180)
    arguments = parser.parse_args()
    search(arguments.max_nodes, arguments.max_depth)
