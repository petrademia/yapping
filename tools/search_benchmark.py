"""Reproducible exact-search complexity and compute-quality benchmark.

Records measurable search statistics for fixed scenarios across node budgets.
Does not train models or claim guided-search speedups.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from matchup_config import load_config
from search_opening import run_search
from trace_albaz_combo import ROOT, SCRIPTS
from yapping import SearchStats, report_provenance
from yapping.benchmark import aggregate_budget_rows, summarize_search_stats


ROOT_DIR = Path(__file__).parents[1]
DEFAULT_BENCHMARK = ROOT_DIR / "configs/benchmarks/albaz_search_baseline.json"


def load_benchmark(path=None):
    source = Path(path) if path else DEFAULT_BENCHMARK
    data = json.loads(source.read_text(encoding="utf-8"))
    data["_path"] = str(source.resolve())
    return data


def run_case(scenario, *, max_nodes, max_depth, config, replay_mode):
    stats = SearchStats()
    started = time.perf_counter()
    result, final, _ = run_search(
        interruption=scenario["interruption"],
        max_nodes=max_nodes,
        max_depth=max_depth,
        opening_hand=scenario.get("opening_hand"),
        ecclesia_copies=int(scenario.get("ecclesia_copies", 1)),
        config=config,
        replay_mode=replay_mode,
        stats=stats,
    )
    runtime = time.perf_counter() - started
    return {
        "scenario_id": scenario["scenario_id"],
        "interruption": scenario["interruption"],
        "opening_hand": scenario.get("opening_hand"),
        "search_algorithm": "minimax_replay_alphabeta",
        "replay_mode": replay_mode,
        "max_nodes": max_nodes,
        "max_depth": max_depth,
        "visited_states": result.visited_states,
        "complete": result.complete,
        "score": result.score,
        "best_line_length": len(result.actions),
        "runtime_seconds": runtime,
        "search_stats": summarize_search_stats(stats.as_dict()),
        "endboard": final.zones,
    }


def run_benchmark(benchmark, config=None):
    matchup_name = benchmark.get("matchup_config", "albaz.json")
    config_path = ROOT_DIR / "configs" / matchup_name
    config = config or load_config(config_path)
    replay_mode = benchmark.get("replay_mode", "cursor")
    max_depth = int(benchmark.get("max_depth", 180))
    budgets = [int(value) for value in benchmark.get("node_budgets", (1000, 5000, 10000, 50000))]
    rows = []
    for scenario in benchmark["scenarios"]:
        for max_nodes in budgets:
            rows.append(run_case(
                scenario,
                max_nodes=max_nodes,
                max_depth=max_depth,
                config=config,
                replay_mode=replay_mode,
            ))
    complete = all(row["complete"] for row in rows)
    return {
        "benchmark": benchmark.get("name"),
        "benchmark_path": benchmark.get("_path"),
        "matchup_config": str(config_path),
        "provenance": report_provenance(
            database=ROOT / "assets/cards.cdb",
            scripts=SCRIPTS,
            max_nodes=max(budgets) if budgets else 0,
            max_depth=max_depth,
            complete=complete,
            revision_root=ROOT_DIR,
        ),
        "metrics_note": (
            "Branching is search-relevant legal-action count after skip/dedup in "
            "search_opening.legal. Runtime includes replay reconstruction. "
            "future_guided_comparison fields stay null until Level 8 guidance exists."
        ),
        "oracle_data_readiness": {
            "schema_version": 2,
            "available_fields": [
                "state_key", "observation", "legal_actions", "oracle_action",
                "oracle_value", "oracle_action_values", "complete",
                "search_limits", "provenance",
            ],
            "gaps": [
                "Per-state full action-value tables exist only at the search root; "
                "deeper trajectory states currently pin the chosen action's value.",
                "No standardized multi-scenario oracle export tied to this benchmark yet.",
            ],
        },
        "aggregate": aggregate_budget_rows(rows),
        "runs": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK))
    parser.add_argument("--config", default=None, help="optional matchup config override")
    parser.add_argument(
        "--budgets",
        default=None,
        help="comma-separated max_nodes overrides, e.g. 1000,5000,10000",
    )
    args = parser.parse_args()
    benchmark = load_benchmark(args.benchmark)
    if args.budgets:
        benchmark["node_budgets"] = [
            int(part.strip()) for part in args.budgets.split(",") if part.strip()
        ]
    config = load_config(args.config) if args.config else None
    report = run_benchmark(benchmark, config=config)
    print(json.dumps(report, indent=2, sort_keys=True))
