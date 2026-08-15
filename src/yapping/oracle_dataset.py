"""Audit helpers for oracle-labelled policy/value datasets."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from .learning import validate_example


def action_value_coverage(row: Mapping[str, Any]) -> dict[str, bool]:
    legal_set = {str(index) for index in row["legal_actions"]}
    labelled = set(row["oracle_action_values"])
    return {
        "full_legal_coverage": labelled == legal_set,
        "chosen_only": labelled == {str(row["oracle_action"])},
    }


def oracle_action_kind(row: Mapping[str, Any]) -> str:
    legal_actions = row.get("observation", {}).get("legal_actions") or []
    indices = row.get("observation", {}).get("legal_action_indices") or row["legal_actions"]
    if row["oracle_action"] in indices:
        position = list(indices).index(row["oracle_action"])
        if position < len(legal_actions):
            return str(legal_actions[position].get("kind", "?"))
    return "?"


def audit_oracle_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize diversity, label quality, and leakage risk for oracle rows."""
    for row in rows:
        validate_example(row)

    unique_states = {row["state_key"] for row in rows}
    depths = Counter(int(row.get("depth", -1)) for row in rows)
    interruptions = Counter(row.get("scenario_id", row.get("interruption")) for row in rows)
    hand_ids = Counter(row.get("hand_id") for row in rows if row.get("hand_id"))
    opening_hands = Counter(
        tuple(row["opening_hand"]) for row in rows if row.get("opening_hand") is not None
    )
    kinds = Counter(oracle_action_kind(row) for row in rows)
    coverages = [action_value_coverage(row) for row in rows]

    single_legal = [row for row in rows if len(row["legal_actions"]) <= 1]
    multi_legal = [row for row in rows if len(row["legal_actions"]) > 1]
    multi_full = [
        row for row in multi_legal if action_value_coverage(row)["full_legal_coverage"]
    ]
    multi_chosen = [
        row for row in multi_legal if action_value_coverage(row)["chosen_only"]
    ]
    complete = [row for row in rows if row["complete"]]
    incomplete = [row for row in rows if not row["complete"]]
    pass_count = kinds.get("pass", 0)

    state_to_hands: dict[str, set[str]] = defaultdict(set)
    state_to_scenarios: dict[str, set[str]] = defaultdict(set)
    state_to_trajectories: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        key = row["state_key"]
        if row.get("hand_id"):
            state_to_hands[key].add(row["hand_id"])
        scenario = row.get("scenario_id", row.get("interruption"))
        if scenario is not None:
            state_to_scenarios[key].add(str(scenario))
        if row.get("trajectory_id"):
            state_to_trajectories[key].add(row["trajectory_id"])

    cross_hand_states = sum(1 for groups in state_to_hands.values() if len(groups) > 1)
    cross_scenario_states = sum(
        1 for groups in state_to_scenarios.values() if len(groups) > 1
    )
    cross_trajectory_states = sum(
        1 for groups in state_to_trajectories.values() if len(groups) > 1
    )

    unique_hands = len(hand_ids) or len(opening_hands)
    states_per_hand = (
        len(unique_states) / unique_hands if unique_hands else 0.0
    )
    multi_legal_unique_states = len({row["state_key"] for row in multi_legal})

    return {
        "total_examples": len(rows),
        "unique_state_keys": len(unique_states),
        "duplicate_state_rows": len(rows) - len(unique_states),
        "duplicate_state_rate": (
            (len(rows) - len(unique_states)) / len(rows) if rows else 0.0
        ),
        "unique_opening_hands": unique_hands,
        "unique_hand_ids": len(hand_ids),
        "states_per_hand": states_per_hand,
        "single_legal_examples": len(single_legal),
        "multi_legal_examples": len(multi_legal),
        "multi_legal_percentage": (
            100.0 * len(multi_legal) / len(rows) if rows else 0.0
        ),
        "unique_multi_legal_states": multi_legal_unique_states,
        "unique_oracle_actions": len({row["oracle_action"] for row in rows}),
        "oracle_action_kind_distribution": dict(kinds),
        "pass_percentage": (100.0 * pass_count / len(rows) if rows else 0.0),
        "depth_distribution": dict(sorted(depths.items())),
        "interruption_distribution": dict(interruptions),
        "opening_hand_distribution_top": {
            str(list(hand)): count
            for hand, count in opening_hands.most_common(20)
        },
        "hand_id_distribution_top": dict(hand_ids.most_common(20)),
        "complete_examples": len(complete),
        "incomplete_examples": len(incomplete),
        "examples_with_full_action_value_labels": sum(
            item["full_legal_coverage"] for item in coverages
        ),
        "examples_with_chosen_action_only_labels": sum(
            item["chosen_only"] for item in coverages
        ),
        "multi_legal_full_action_values": len(multi_full),
        "multi_legal_chosen_only": len(multi_chosen),
        "leakage": {
            "state_keys_shared_across_hands": cross_hand_states,
            "state_keys_shared_across_scenarios": cross_scenario_states,
            "state_keys_shared_across_trajectories": cross_trajectory_states,
        },
        "note": (
            "Full action-value tables are expected mainly at depth 0 from "
            "minimax root_action_values; deeper states typically label only "
            "the chosen action. Behavior cloning needs (s, a*), not full Q."
        ),
    }


def load_jsonl(path) -> list[dict[str, Any]]:
    from pathlib import Path

    rows = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            import json

            rows.append(json.loads(line))
    return rows
