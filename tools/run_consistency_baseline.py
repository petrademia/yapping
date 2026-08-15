"""Practical Level-3 consistency slice for readiness experiments.

Runs unique-hand sampling against none/ash/impermanence only so the
experiment finishes in reasonable wall time while preserving conditioned
and quantified reporting semantics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyze_consistency import (
    analyze,
    attach_baseline_deltas,
    init_worker,
    sample_hands,
)
from matchup_config import load_config
from trace_albaz_combo import ROOT, SCRIPTS
from yapping import (
    conditioned_hand_utility,
    normalize_card_roles,
    quantified_hand_report,
    report_provenance,
    role_density_opening_profile,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hands", type=int, default=16)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-nodes", type=int, default=20_000)
    parser.add_argument("--max-depth", type=int, default=180)
    parser.add_argument("--config", default=None)
    parser.add_argument(
        "--interruptions",
        default="none,ash,impermanence",
        help="comma-separated interruptions; none is added if missing",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    interruptions = [name.strip() for name in args.interruptions.split(",") if name.strip()]
    if "none" not in interruptions:
        interruptions = ["none", *interruptions]
    hands = list(sample_hands(config["main_deck"], args.hands, args.seed))
    init_worker()
    reports = {}
    for interruption in interruptions:
        rows, summary = analyze(
            config, hands, interruption, args.max_nodes, args.max_depth
        )
        reports[interruption] = {"summary": summary, "hands": rows}
    attach_baseline_deltas(reports)
    conditioned = {
        name: conditioned_hand_utility(report["hands"])
        for name, report in reports.items()
    }
    quantified = quantified_hand_report(
        reports, thresholds=(5.0, 10.0, 15.0), interruption_weights=None
    )
    role_density = None
    card_roles = normalize_card_roles(config.get("card_roles"))
    if card_roles:
        role_density = role_density_opening_profile(config["main_deck"], card_roles)
    complete = all(
        row["complete"]
        for report in reports.values()
        for row in report["hands"]
    )
    payload = {
        "config": config["name"],
        "experiment": {
            "hands": args.hands,
            "seed": args.seed,
            "max_nodes": args.max_nodes,
            "max_depth": args.max_depth,
            "interruptions": interruptions,
            "note": (
                "Unique-hand sample; evaluated_probability_mass is not full-deck "
                "coverage. Interruptions limited for wall-time practicality."
            ),
        },
        "provenance": report_provenance(
            database=ROOT / "assets/cards.cdb",
            scripts=SCRIPTS,
            max_nodes=args.max_nodes,
            max_depth=args.max_depth,
            complete=complete,
            revision_root=Path(__file__).parents[1],
        ),
        "reports": reports,
        "conditioned": conditioned,
        "quantified": quantified,
    }
    if role_density is not None:
        payload["role_density"] = role_density
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
