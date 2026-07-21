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


def summarize(rows):
    total_weight = sum(row["probability"] for row in rows) or 1
    categories = ("board_value", "interaction_value", "follow_up_value", "survival_value")
    summary = {
        "hands": len(rows),
        "weighted_score": sum(row["score"] * row["probability"] for row in rows) / total_weight,
        "weighted_categories": {
            category: sum(row["categories"][category] * row["probability"] for row in rows) / total_weight
            for category in categories
        },
        "complete_fraction": sum(row["complete"] for row in rows) / len(rows) if rows else 0,
        "brick_fraction": sum(row["classification"]["brick"] for row in rows) / len(rows) if rows else 0,
        "provisional_hands": sum(not row["complete"] for row in rows),
    }
    paired = [row for row in rows if "score_loss" in row]
    if paired:
        paired_weight = sum(row["probability"] for row in paired) or 1
        summary["paired_hands"] = len(paired)
        summary["weighted_score_loss"] = sum(
            row["score_loss"] * row["probability"] for row in paired
        ) / paired_weight
        summary["weighted_category_loss"] = {
            category: sum(row["category_deltas"][category] * row["probability"] for row in paired)
            / paired_weight
            for category in categories
        }
    return summary


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
    return rows, summarize(rows)


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


def attach_baseline_deltas(reports):
    """Pair each interruption row with the result for the identical hand."""
    baseline = {
        tuple(row["hand"]): row
        for row in reports.get("none", {}).get("hands", [])
    }
    for name, report in reports.items():
        if name == "none":
            continue
        for row in report["hands"]:
            reference = baseline.get(tuple(row["hand"]))
            if reference is None:
                continue
            row["baseline_score"] = reference["score"]
            row["score_loss"] = reference["score"] - row["score"]
            row["category_deltas"] = {
                category: reference["categories"][category] - row["categories"][category]
                for category in reference["categories"]
                if category != "total_score"
            }
        if report["hands"]:
            paired = [row for row in report["hands"] if "score_loss" in row]
            report["summary"].update(summarize(report["hands"]))


def add_extender_marginals(reports, config, max_nodes, max_depth):
    """Measure configured extenders by replacing one copy with filler."""
    extenders = [int(card) for card in config.get("extenders", [])]
    filler = int(config.get("counterfactual_filler", 91152256))
    if not extenders:
        return
    adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    for report in reports.values():
        for row in report["hands"]:
            row["extender_marginals"] = {}
            for extender in extenders:
                if extender not in row["hand"]:
                    continue
                counterfactual = list(row["hand"])
                counterfactual[counterfactual.index(extender)] = filler
                with contextlib.redirect_stdout(io.StringIO()):
                    result, final = search(
                        row["interruption"], max_nodes=max_nodes,
                        max_depth=max_depth, opening_hand=counterfactual,
                        config=config, adapter=adapter,
                    )
                counter_categories = score_categories(final, config=config)
                row["extender_marginals"][str(extender)] = {
                    "score_delta": row["score"] - result.score,
                    "counterfactual_score": result.score,
                    "counterfactual_complete": result.complete,
                    "category_deltas": {
                        category: row["categories"][category] - counter_categories[category]
                        for category in ("board_value", "interaction_value",
                                          "follow_up_value", "survival_value")
                    },
                }
    del adapter


def aggregate_extenders(reports):
    for report in reports.values():
        values = {}
        for row in report["hands"]:
            for card, result in row.get("extender_marginals", {}).items():
                values.setdefault(card, []).append(result)
        report["summary"]["extenders"] = {
            card: {
                "observations": len(results),
                "mean_score_delta": sum(item["score_delta"] for item in results) / len(results),
                "mean_category_deltas": {
                    category: sum(item["category_deltas"][category] for item in results) / len(results)
                    for category in ("board_value", "interaction_value", "follow_up_value", "survival_value")
                },
            }
            for card, results in values.items()
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--interruption", default="all")
    parser.add_argument("--hands", type=int, default=4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-nodes", type=int, default=100)
    parser.add_argument("--max-depth", type=int, default=40)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--extenders", action="store_true")
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
            reports[interruption] = {
                "summary": summarize(grouped_rows), "hands": grouped_rows,
            }
    else:
        for interruption in interruptions:
            rows, summary = analyze(config, hands, interruption,
                                    args.max_nodes, args.max_depth)
            reports[interruption] = {"summary": summary, "hands": rows}
    attach_baseline_deltas(reports)
    if args.extenders:
        if args.workers > 1:
            raise ValueError("--extenders currently requires --workers 1")
        add_extender_marginals(reports, config, args.max_nodes, args.max_depth)
        aggregate_extenders(reports)
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
