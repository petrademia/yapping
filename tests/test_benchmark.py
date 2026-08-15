"""Portable tests for search measurement helpers (no OCGCore)."""

from yapping import SearchStats, minimax_replay
from yapping.benchmark import (
    aggregate_budget_rows,
    compute_quality_curve,
    future_guided_comparison_template,
    summarize_branching,
    summarize_branching_by_depth,
    summarize_search_stats,
)


def test_summarize_branching_empty_and_basic():
    empty = summarize_branching([])
    assert empty["observations"] == 0
    assert empty["mean"] is None
    summary = summarize_branching([2, 4, 4, 10])
    assert summary["observations"] == 4
    assert summary["mean"] == 5.0
    assert summary["median"] == 4.0
    assert summary["maximum"] == 10.0
    assert summary["minimum"] == 2.0


def test_summarize_branching_by_depth_bands():
    report = summarize_branching_by_depth({
        0: [2],
        3: [4],
        7: [8, 10],
        15: [12],
    })
    assert report["by_depth"]["7"]["mean"] == 9.0
    assert report["by_band"]["0-5"]["observations"] == 2
    assert report["by_band"]["6-10"]["mean"] == 9.0
    assert "search-relevant" in report["note"]


def test_summarize_search_stats_without_collector():
    assert summarize_search_stats(None)["available"] is False


def test_compute_quality_curve_orders_by_budget():
    rows = [
        {"scenario_id": "a", "interruption": "ash", "max_nodes": 5000,
         "complete": True, "score": 8.0, "runtime_seconds": 0.2,
         "visited_states": 100, "best_line_length": 10, "max_depth": 40},
        {"scenario_id": "a", "interruption": "ash", "max_nodes": 1000,
         "complete": False, "score": 6.0, "runtime_seconds": 0.1,
         "visited_states": 50, "best_line_length": 8, "max_depth": 40},
    ]
    curve = compute_quality_curve(rows)
    assert [row["max_nodes"] for row in curve] == [1000, 5000]
    aggregate = aggregate_budget_rows(rows)
    assert aggregate["runs"] == 2
    assert aggregate["future_guided_comparison"]["status"].startswith("reserved")


def test_future_guided_comparison_template_has_null_metrics():
    template = future_guided_comparison_template()
    assert template["fields"]["search_speedup"] is None
    assert template["fields"]["utility_gap"] is None


def test_minimax_search_stats_collect_branching_and_tt():
    # Tiny deterministic tree: root -> two children -> terminals.
    def replay(path):
        depth = len(path)
        return {"key": f"d{depth}:{path}", "depth": depth, "path": path}

    def legal_actions(node):
        return (0, 1) if node["depth"] < 2 else ()

    def evaluate(node):
        return float(sum(node["path"]) if node["path"] else 0)

    def terminal(node):
        return node["depth"] >= 2

    def owner(_node):
        return 0

    stats = SearchStats()
    result = minimax_replay(
        replay, legal_actions, evaluate, terminal, owner,
        max_depth=4, max_nodes=100, stats=stats,
    )
    assert result.complete
    assert result.stats is stats
    assert stats.visited_states == result.visited_states
    assert stats.expanded_internal_nodes >= 1
    assert stats.branching_factors
    assert summarize_branching(stats.branching_factors)["mean"] == 2.0
    assert stats.tt_hits + stats.tt_misses > 0
    assert stats.leaf_evaluations >= 1
