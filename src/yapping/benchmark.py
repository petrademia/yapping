"""Search measurement helpers: branching summaries and compute-quality curves.

These utilities summarize instrumentation collected during exact search.
They do not implement MCTS, RL, or policy guidance. Future guided-search
comparisons should reuse the same scenario IDs and budget fields.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from statistics import mean, median
from typing import Any


def _percentile(sorted_values: Sequence[float], quantile: float) -> float | None:
    if not sorted_values:
        return None
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be in [0, 1]")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = quantile * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return float(sorted_values[lower]) * (1.0 - weight) + float(sorted_values[upper]) * weight


def summarize_branching(factors: Sequence[int | float]) -> dict[str, Any]:
    """Summarize legal branching factors observed at expanded internal nodes.

    Empty input returns null statistics rather than inventing zeros that look
    like measured branching.
    """
    values = [float(factor) for factor in factors]
    if not values:
        return {
            "observations": 0,
            "mean": None,
            "median": None,
            "p90": None,
            "maximum": None,
            "minimum": None,
        }
    ordered = sorted(values)
    return {
        "observations": len(values),
        "mean": mean(values),
        "median": median(values),
        "p90": _percentile(ordered, 0.90),
        "maximum": ordered[-1],
        "minimum": ordered[0],
    }


def summarize_branching_by_depth(
    branching_by_depth: Mapping[int, Sequence[int | float]],
) -> dict[str, Any]:
    """Per-depth branching summaries plus optional coarse depth bands."""
    by_depth = {
        str(depth): summarize_branching(factors)
        for depth, factors in sorted(branching_by_depth.items(), key=lambda item: item[0])
    }
    bands = ((0, 5), (6, 10), (11, 20), (21, 40), (41, 10**9))
    band_factors: dict[str, list[float]] = defaultdict(list)
    for depth, factors in branching_by_depth.items():
        for low, high in bands:
            if low <= int(depth) <= high:
                label = f"{low}-{high if high < 10**9 else 'plus'}"
                band_factors[label].extend(float(factor) for factor in factors)
                break
    return {
        "by_depth": by_depth,
        "by_band": {
            label: summarize_branching(factors)
            for label, factors in band_factors.items()
        },
        "note": (
            "Branching counts search-relevant legal actions passed to minimax "
            "(after tool-level skip/dedup). Raw protocol prompt counts are not "
            "included unless a separate raw_legal_count callback is supplied."
        ),
    }


def summarize_search_stats(stats: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize a SearchStats-like mapping into a JSON-friendly report block."""
    if not stats:
        return {
            "available": False,
            "note": "No SearchStats were collected for this run.",
        }
    branching = stats.get("search_relevant_branching") or stats.get("branching_factors") or ()
    by_depth = stats.get("branching_by_depth") or {}
    return {
        "available": True,
        "visited_states": stats.get("visited_states"),
        "expanded_internal_nodes": stats.get("expanded_internal_nodes"),
        "terminal_states": stats.get("terminal_states"),
        "leaf_evaluations": stats.get("leaf_evaluations"),
        "cutoffs": stats.get("cutoffs"),
        "tt_hits": stats.get("tt_hits"),
        "tt_misses": stats.get("tt_misses"),
        "tt_entries": stats.get("tt_entries"),
        "max_depth_reached": stats.get("max_depth_reached"),
        "branching": summarize_branching(list(branching)),
        "branching_by_depth": summarize_branching_by_depth(
            {int(depth): list(factors) for depth, factors in by_depth.items()}
        ),
    }


def compute_quality_curve(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Order budget-sweep rows for the compute → completeness/utility curve."""
    ordered = sorted(
        rows,
        key=lambda row: (
            int(row.get("max_nodes", 0)),
            str(row.get("scenario_id", "")),
            str(row.get("interruption", "")),
        ),
    )
    curve = []
    for row in ordered:
        curve.append({
            "scenario_id": row.get("scenario_id"),
            "interruption": row.get("interruption"),
            "max_nodes": row.get("max_nodes"),
            "max_depth": row.get("max_depth"),
            "visited_states": row.get("visited_states"),
            "complete": row.get("complete"),
            "score": row.get("score"),
            "runtime_seconds": row.get("runtime_seconds"),
            "best_line_length": row.get("best_line_length"),
        })
    return curve


def future_guided_comparison_template() -> dict[str, Any]:
    """Schema reserved for Level 8 policy-guided vs exact-oracle comparisons.

    Values stay null until a learned guide exists. Do not invent speedups.
    """
    return {
        "status": "reserved_until_policy_guidance_exists",
        "fields": {
            "baseline_nodes": None,
            "guided_nodes": None,
            "baseline_runtime": None,
            "guided_runtime": None,
            "oracle_utility": None,
            "guided_utility": None,
            "search_speedup": None,
            "utility_gap": None,
        },
        "definitions": {
            "search_speedup": "baseline_nodes / guided_nodes",
            "utility_gap": "oracle_utility - guided_utility",
        },
        "note": (
            "Populate only when comparing the same scenario IDs and budgets "
            "against an exact-oracle baseline."
        ),
    }


def aggregate_budget_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate a benchmark run for reporting."""
    material = list(rows)
    return {
        "runs": len(material),
        "compute_quality_curve": compute_quality_curve(material),
        "future_guided_comparison": future_guided_comparison_template(),
    }
