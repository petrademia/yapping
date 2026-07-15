"""Estimate configured-deck consistency over sampled opening hands."""

import argparse
import contextlib
import gc
import io
import json
import math
import random
from collections import Counter

from matchup_config import load_config
from search_opening import search


def hand_probability(deck, hand, hand_size=5):
    counts = Counter(deck)
    numerator = math.prod(math.comb(counts[card], amount)
                          for card, amount in Counter(hand).items())
    return numerator / math.comb(len(deck), hand_size)


def sample_hands(deck, amount, seed):
    rng = random.Random(seed)
    seen = set()
    while len(seen) < amount:
        hand = tuple(sorted(rng.sample(deck, 5)))
        if hand not in seen:
            seen.add(hand)
            yield hand


def classify(hand, config):
    anchors = set(config.get("anchors", []))
    garnets = set(config.get("garnets", []))
    return {
        "brick": not bool(anchors.intersection(hand)),
        "garnets": sorted(garnets.intersection(hand)),
    }


def analyze(config, hands, interruption, max_nodes, max_depth):
    rows = []
    for hand in hands:
        with contextlib.redirect_stdout(io.StringIO()):
            result, final = search(
                interruption,
                max_nodes=max_nodes,
                max_depth=max_depth,
                opening_hand=list(hand),
                config=config,
            )
        gc.collect()
        rows.append({
            "hand": list(hand),
            "probability": hand_probability(config["main_deck"], hand),
            "classification": classify(hand, config),
            "score": result.score,
            "complete": result.complete,
            "visited_states": result.visited_states,
            "endboard": final.zones,
        })
    total_weight = sum(row["probability"] for row in rows) or 1
    return rows, {
        "hands": len(rows),
        "weighted_score": sum(row["score"] * row["probability"] for row in rows) / total_weight,
        "complete_fraction": sum(row["complete"] for row in rows) / len(rows) if rows else 0,
        "brick_fraction": sum(row["classification"]["brick"] for row in rows) / len(rows) if rows else 0,
        "provisional_hands": sum(not row["complete"] for row in rows),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--interruption", default="all")
    parser.add_argument("--hands", type=int, default=4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-nodes", type=int, default=100)
    parser.add_argument("--max-depth", type=int, default=40)
    args = parser.parse_args()
    config = load_config(args.config)
    hands = list(sample_hands(config["main_deck"], args.hands, args.seed))
    interruptions = (list(config["interruptions"])
                     if args.interruption == "all" else [args.interruption])
    reports = {}
    for interruption in interruptions:
        rows, summary = analyze(config, hands, interruption,
                                args.max_nodes, args.max_depth)
        reports[interruption] = {"summary": summary, "hands": rows}
    print(json.dumps({"config": config["name"], "reports": reports},
                     indent=2, sort_keys=True))
