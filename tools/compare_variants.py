"""Compare one-slot deck variants on the same opening-hand sample."""

import argparse
import copy
import json

from analyze_consistency import analyze, init_worker, sample_hands
from matchup_config import load_config, scenarios
from yapping import DeckVariant, SlotCandidate, load_archetype, summarize_compendium


def parse_candidate(value):
    card, role, *label = value.split(":", 2)
    return SlotCandidate(int(card), role, label[0] if label else "")


def compare(config, candidates, remove_card, hands, interruption, max_nodes, max_depth,
            turn_orders=(0, 1)):
    base = DeckVariant.from_config(config)
    variants = [(base.name, base)] + [
        (variant.name, variant) for variant in base.variants(candidates, remove_card)
    ]
    all_reports = {}
    for controlled_player in turn_orders:
        reports = {}
        for name, variant in variants:
            variant_config = copy.deepcopy(config)
            variant_config["name"] = name
            variant_config["main_deck"] = list(variant.main_deck)
            rows, summary = analyze(variant_config, hands, interruption, max_nodes,
                                    max_depth, controlled_player)
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
        all_reports["first" if controlled_player == 0 else "second"] = reports
    return all_reports


def weighted_compare(config, candidates, remove_card, hands, max_nodes, max_depth,
                     turn_orders=(0, 1), requested=None):
    """Evaluate each variant in configured opponent worlds and aggregate EV."""
    worlds = scenarios(config, requested)
    result = {}
    for controlled_player in turn_orders:
        variants = [(DeckVariant.from_config(config).name, DeckVariant.from_config(config))]
        base = variants[0][1]
        variants += [(variant.name, variant)
                     for variant in base.variants(candidates, remove_card)]
        reports = {}
        for name, variant in variants:
            world_reports = {}
            variant_config = copy.deepcopy(config)
            variant_config["name"] = name
            variant_config["main_deck"] = list(variant.main_deck)
            for world in worlds:
                world_config = copy.deepcopy(variant_config)
                if world.get("opponent_deck") is not None:
                    world_config["opponent_deck"] = world["opponent_deck"]
                rows, summary = analyze(world_config, hands, world["interruption"],
                                         max_nodes, max_depth, controlled_player)
                world_reports[world["name"]] = {
                    "weight": world["weight"], "summary": summary, "hands": rows,
                }
            reports[name] = {"scenarios": world_reports}
        baseline = reports[base.name]
        for name, report in reports.items():
            def expected(field):
                return sum(world["weight"] * world["summary"][field]
                           for world in report["scenarios"].values())
            report["summary"] = {
                "weighted_score": expected("weighted_score"),
                "weighted_categories": {
                    category: sum(world["weight"] * world["summary"]["weighted_categories"][category]
                                  for world in report["scenarios"].values())
                    for category in baseline["scenarios"][worlds[0]["name"]]["summary"]["weighted_categories"]
                },
                "brick_fraction": expected("brick_fraction"),
                "complete_fraction": expected("complete_fraction"),
            }
            report["delta_vs_baseline"] = {
                "weighted_score": report["summary"]["weighted_score"] - baseline.get("summary", {}).get("weighted_score", 0),
            }
        result["first" if controlled_player == 0 else "second"] = reports
    return result


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
    parser.add_argument("--turn-order", choices=["first", "second", "both"], default="both")
    parser.add_argument("--weighted", action="store_true")
    parser.add_argument("--archetype", default=None,
                        help="verified archetype JSON used to annotate candidates")
    args = parser.parse_args()
    config = load_config(args.config)
    hands = list(sample_hands(config["main_deck"], args.hands, args.seed))
    init_worker()
    turn_orders = {"first": (0,), "second": (1,), "both": (0, 1)}[args.turn_order]
    candidates = [parse_candidate(value) for value in args.candidate]
    if args.weighted:
        result = weighted_compare(config, candidates, args.replace, hands,
                                  args.max_nodes, args.max_depth, turn_orders,
                                  ([args.interruption] if args.interruption != "ash"
                                   else ["none", *config["interruptions"]]))
    else:
        result = compare(config, candidates, args.replace, hands, args.interruption,
                         args.max_nodes, args.max_depth, turn_orders)
    output = {"config": config["name"], "interruption": args.interruption,
              "hands": [list(hand) for hand in hands], "reports": result}
    if args.archetype:
        output["compendium"] = summarize_compendium(load_archetype(args.archetype), candidates)
    print(json.dumps(output,
                     indent=2, sort_keys=True))
