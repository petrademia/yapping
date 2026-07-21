"""Estimate configured-deck consistency over sampled opening hands."""

import argparse
import contextlib
import gc
import io
import json
import math
import multiprocessing as mp
import random
from collections import Counter

from matchup_config import load_config
from analyze_ash import score_categories
from search_opening import search
from trace_albaz_combo import ROOT, SCRIPTS
from yapping._ocgcore import Duel
from yapping import report_provenance


_worker_adapter = None


def init_worker():
    global _worker_adapter
    _worker_adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))


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
                config=config, adapter=_worker_adapter,
            )
        gc.collect()
        rows.append({
            "hand": list(hand),
            "probability": hand_probability(config["main_deck"], hand),
            "interruption": interruption,
            "classification": classify(hand, config),
            "score": result.score,
            "categories": score_categories(final, config=config),
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


def analyze_job(job):
    config, hand, interruption, max_nodes, max_depth = job
    row = analyze(config, [hand], interruption, max_nodes, max_depth)[0][0]
    gc.collect()
    return row


def analyze_parallel(config, hands, interruptions, max_nodes, max_depth, workers):
    jobs = [(config, hand, interruption, max_nodes, max_depth)
            for interruption in interruptions for hand in hands]
    with mp.Pool(workers, initializer=init_worker) as pool:
        rows = pool.map(analyze_job, jobs)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--interruption", default="all")
    parser.add_argument("--hands", type=int, default=4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-nodes", type=int, default=100)
    parser.add_argument("--max-depth", type=int, default=40)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    config = load_config(args.config)
    hands = list(sample_hands(config["main_deck"], args.hands, args.seed))
    requested = (list(config["interruptions"])
                 if args.interruption == "all" else [args.interruption])
    # Keep the uninterrupted ceiling paired with every interruption scenario.
    interruptions = ["none"] + [name for name in requested if name != "none"]
    reports = {}
    if args.workers > 1:
        rows = analyze_parallel(config, hands, interruptions, args.max_nodes,
                                args.max_depth, args.workers)
        grouped = {interruption: [] for interruption in interruptions}
        for row in rows:
            grouped[row["interruption"]].append(row)
        for interruption, grouped_rows in grouped.items():
            weight = sum(row["probability"] for row in grouped_rows) or 1
            reports[interruption] = {"summary": {
                "hands": len(grouped_rows),
                "weighted_score": sum(row["score"] * row["probability"] for row in grouped_rows) / weight,
                "complete_fraction": sum(row["complete"] for row in grouped_rows) / len(grouped_rows),
                "brick_fraction": sum(row["classification"]["brick"] for row in grouped_rows) / len(grouped_rows),
                "provisional_hands": sum(not row["complete"] for row in grouped_rows),
            }, "hands": grouped_rows}
    else:
        for interruption in interruptions:
            rows, summary = analyze(config, hands, interruption,
                                    args.max_nodes, args.max_depth)
            reports[interruption] = {"summary": summary, "hands": rows}
    complete = all(
        row["complete"]
        for report in reports.values()
        for row in report["hands"]
    )
    print(json.dumps({
        "config": config["name"],
        "provenance": report_provenance(
            database=ROOT / "assets/cards.cdb", scripts=SCRIPTS,
            max_nodes=args.max_nodes, max_depth=args.max_depth,
            complete=complete, revision_root=ROOT,
        ),
        "reports": reports,
    },
                     indent=2, sort_keys=True))
