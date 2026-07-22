"""Compare one-slot deck variants on the same opening-hand sample."""

import argparse
import copy
import json

from analyze_consistency import analyze, init_worker, sample_hands
from matchup_config import load_config
from yapping import DeckVariant, SlotCandidate


def parse_candidate(value):
    card, role, *label = value.split(":", 2)
    return SlotCandidate(int(card), role, label[0] if label else "")


def compare(config, candidates, remove_card, hands, interruption, max_nodes, max_depth):
    base = DeckVariant.from_config(config)
    variants = [(base.name, base)] + [
        (variant.name, variant) for variant in base.variants(candidates, remove_card)
    ]
    reports = {}
    for name, variant in variants:
        variant_config = copy.deepcopy(config)
        variant_config["name"] = name
        variant_config["main_deck"] = list(variant.main_deck)
        rows, summary = analyze(variant_config, hands, interruption, max_nodes, max_depth)
        reports[name] = {"summary": summary, "hands": rows}
    baseline = reports[base.name]["summary"]
    for name, report in reports.items():
        report["delta_vs_baseline"] = {
            "weighted_score": report["summary"]["weighted_score"] - baseline["weighted_score"],
            "weighted_categories": {
                category: report["summary"]["weighted_categories"][category]
                - baseline["weighted_categories"][category]
                for category in baseline["weighted_categories"]
            },
            "brick_fraction": report["summary"]["brick_fraction"] - baseline["brick_fraction"],
        }
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/albaz.json")
    parser.add_argument("--replace", type=int, required=True)
    parser.add_argument("--candidate", action="append", required=True,
                        help="CARD:ROLE:LABEL, repeatable")
    parser.add_argument("--interruption", default="ash")
    parser.add_argument("--hands", type=int, default=4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-nodes", type=int, default=100)
    parser.add_argument("--max-depth", type=int, default=40)
    args = parser.parse_args()
    config = load_config(args.config)
    hands = list(sample_hands(config["main_deck"], args.hands, args.seed))
    init_worker()
    result = compare(config, [parse_candidate(value) for value in args.candidate],
                     args.replace, hands, args.interruption,
                     args.max_nodes, args.max_depth)
    print(json.dumps({"config": config["name"], "interruption": args.interruption,
                      "hands": [list(hand) for hand in hands], "reports": result},
                     indent=2, sort_keys=True))
