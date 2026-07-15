"""Sample hidden opponent worlds and report an uncertainty-aware action choice."""

import argparse
import gc
import json
import random
import statistics

from analyze_ash import endboard_score, replay
from matchup_config import load_config
from search_opening import legal
from trace_albaz_combo import card_id
from yapping import minimax_replay, opening_probability


def action_key(snapshot, index):
    action = snapshot.decision["actions"][index]
    return tuple(action[field] for field in (
        "kind", "card", "controller", "location", "sequence", "description",
    ))


def search(interruption="ash", opening_hand=None, samples=8, seed=7,
           max_nodes=500, max_depth=80, config=None):
    config = config or load_config()
    rng = random.Random(seed)
    worlds = [None, config["interruptions"][interruption]]
    copies = config.get("opponent_copies", {}).get(interruption, 0)
    p_interruption = opening_probability(
        config.get("opponent_deck_size", 40), copies,
        config.get("opponent_hand_size", 5),
    )
    sampled = [worlds[1] if rng.random() < p_interruption else worlds[0]
               for _ in range(samples)]
    unique = list(dict.fromkeys(sampled))
    roots = {}
    for world in unique:
        roots[world] = replay((), world, opening_hand, matchup=config)
        gc.collect()
    common = {}
    for world, node in roots.items():
        for index in legal(node, config):
            common.setdefault(action_key(node, index), {})[world] = index
    common = {key: indices for key, indices in common.items()
             if len(indices) == len(unique)}
    reports = []
    for key, indices in common.items():
        values = []
        complete = True
        for world in sampled:
            prefix = (indices[world],)
            result = minimax_replay(
                lambda path, world=world, prefix=prefix:
                    replay(prefix + path, world, opening_hand, matchup=config),
                lambda node: legal(node, config),
                lambda node: endboard_score(node, config["weights"]),
                lambda node: node.decision["turn"] >= 2,
                lambda node: node.decision["player"],
                max_depth=max_depth - 1, max_nodes=max_nodes,
            )
            values.append(result.score)
            complete &= result.complete
        reports.append({"action": key, "mean": statistics.fmean(values),
                        "complete": complete, "samples": len(values),
                        "values": values})
    reports.sort(key=lambda row: row["mean"], reverse=True)
    chosen = reports[0] if reports else None
    values = chosen["values"] if chosen else []
    stderr = (statistics.stdev(values) / len(values) ** 0.5
              if len(values) > 1 else 0.0)
    return {"mode": "sampled_determinization", "interruption": interruption,
            "interruption_probability": p_interruption,
            "sample_count": samples, "seed": seed, "worlds": sampled,
            "chosen": chosen, "stderr": stderr,
            "confidence_95": [chosen["mean"] - 1.96 * stderr,
                              chosen["mean"] + 1.96 * stderr] if chosen else None,
            "all_candidates": reports}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("interruption", default="ash")
    parser.add_argument("--hand", type=card_id, nargs=5)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-nodes", type=int, default=500)
    parser.add_argument("--max-depth", type=int, default=80)
    parser.add_argument("--config")
    args = parser.parse_args()
    print(json.dumps(search(args.interruption, args.hand, args.samples, args.seed,
                            args.max_nodes, args.max_depth, load_config(args.config)),
                     indent=2, sort_keys=True))
