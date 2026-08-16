"""Portable tests for hand sampling, matchup wiring, and oracle dataset audit."""

import json

import pytest

from matchup_config import experiment_matchup
from yapping import (
    audit_oracle_rows,
    hand_id,
    sample_unique_hands,
    trajectory_id,
    validate_example,
    validate_hand_in_deck,
)


def test_experiment_matchup_uses_configured_deck_for_opening_hands():
    config = {"main_deck": [1] * 40, "name": "demo"}
    assert experiment_matchup(config, opening_hand=[1, 1, 1, 1, 1]) is config
    assert experiment_matchup(config, opening_hand=None) is None


def test_experiment_matchup_preserves_fixture_default_and_flags():
    config = {"main_deck": [1] * 40, "use_fixture_deck": True}
    assert experiment_matchup(config, opening_hand=[1, 1, 1, 1, 1]) is None
    forced = {"main_deck": [1] * 40, "use_configured_deck": True}
    assert experiment_matchup(forced, opening_hand=None) is forced
    legacy = {"main_deck": [1] * 40, "opponent_deck": [2] * 40}
    assert experiment_matchup(legacy, opening_hand=None) is legacy


def test_validate_hand_in_deck_accepts_subset_and_rejects_missing():
    deck = [10, 20, 20, 30, 40] + [99] * 35
    validate_hand_in_deck(deck, [10, 20, 20, 30, 40])
    with pytest.raises(ValueError, match="not in this deck"):
        validate_hand_in_deck(deck, [10, 20, 20, 30, 50])
    with pytest.raises(ValueError, match="exactly five"):
        validate_hand_in_deck(deck, [10, 20, 30])


def test_sample_unique_hands_is_deterministic_and_seed_sensitive():
    deck = list(range(40))
    first = list(sample_unique_hands(deck, 8, seed=7))
    second = list(sample_unique_hands(deck, 8, seed=7))
    third = list(sample_unique_hands(deck, 8, seed=8))
    assert first == second
    assert first != third
    assert len(set(first)) == 8
    assert all(len(hand) == 5 for hand in first)


def test_hand_and_trajectory_ids_are_stable_across_serialization():
    hand = [3, 1, 2, 2, 5]
    hid = hand_id(hand)
    assert hid == hand_id(sorted(hand))
    tid = trajectory_id(hid, "ash", max_nodes=50_000, max_depth=180)
    row = {
        "schema_version": 2,
        "observation": {},
        "state_key": "aa",
        "legal_actions": [0, 1],
        "oracle_action": 1,
        "oracle_value": 8.0,
        "oracle_action_values": {"1": 8.0},
        "complete": True,
        "search_limits": {"max_nodes": 50_000, "max_depth": 180},
        "hand_id": hid,
        "scenario_id": "ash",
        "trajectory_id": tid,
        "opening_hand": list(hand),
        "provenance": {
            "hand_id": hid,
            "scenario_id": "ash",
            "trajectory_id": tid,
            "opening_hand": list(hand),
        },
    }
    validate_example(row)
    restored = json.loads(json.dumps(row, sort_keys=True))
    assert restored["hand_id"] == hid
    assert restored["trajectory_id"] == tid
    assert restored["provenance"]["hand_id"] == hid


def _example(
    *,
    state_key,
    legal,
    action,
    kind="activate",
    complete=True,
    hand_id_value="h1",
    scenario="ash",
    depth=0,
    full_values=False,
):
    action_values = {str(action): 1.0}
    if full_values:
        action_values = {str(index): float(index) for index in legal}
    return {
        "schema_version": 2,
        "observation": {
            "legal_action_indices": list(legal),
            "legal_actions": [{"kind": kind} for _ in legal],
        },
        "state_key": state_key,
        "legal_actions": list(legal),
        "oracle_action": action,
        "oracle_value": 1.0,
        "oracle_action_values": action_values,
        "complete": complete,
        "depth": depth,
        "interruption": scenario,
        "scenario_id": scenario,
        "hand_id": hand_id_value,
        "trajectory_id": f"{hand_id_value}-{scenario}",
        "opening_hand": [1, 2, 3, 4, 5],
        "search_limits": {"max_nodes": 1, "max_depth": 1},
        "provenance": {},
    }


def test_audit_counts_multi_legal_pass_and_duplicates():
    rows = [
        _example(state_key="a", legal=[0], action=0, kind="pass", hand_id_value="h1"),
        _example(
            state_key="b",
            legal=[0, 1],
            action=1,
            kind="activate",
            hand_id_value="h1",
            full_values=True,
        ),
        _example(
            state_key="b",
            legal=[0, 1],
            action=0,
            kind="pass",
            hand_id_value="h2",
            scenario="none",
            depth=3,
        ),
        _example(
            state_key="c",
            legal=[0, 2],
            action=2,
            kind="summon",
            hand_id_value="h2",
            scenario="none",
            depth=1,
            complete=False,
        ),
    ]
    audit = audit_oracle_rows(rows)
    assert audit["total_examples"] == 4
    assert audit["unique_state_keys"] == 3
    assert audit["duplicate_state_rows"] == 1
    assert audit["single_legal_examples"] == 1
    assert audit["multi_legal_examples"] == 3
    assert audit["oracle_action_kind_distribution"]["pass"] == 2
    assert audit["multi_legal_full_action_values"] == 1
    assert audit["multi_legal_chosen_only"] == 2
    assert audit["incomplete_examples"] == 1
    assert audit["leakage"]["state_keys_shared_across_hands"] == 1
    assert audit["leakage"]["state_keys_shared_across_scenarios"] == 1


def test_complete_only_filter_excludes_incomplete_rows_from_audit_target():
    complete = _example(state_key="ok", legal=[0, 1], action=0, full_values=True)
    incomplete = _example(
        state_key="bad", legal=[0, 1], action=1, complete=False, depth=2
    )
    kept = [row for row in [complete, incomplete] if row["complete"]]
    audit = audit_oracle_rows(kept)
    assert audit["total_examples"] == 1
    assert audit["incomplete_examples"] == 0
    assert audit["complete_examples"] == 1
