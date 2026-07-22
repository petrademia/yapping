"""Versioned schemas for oracle-labelled policy/value examples."""

from typing import Any, Mapping

ORACLE_SCHEMA_VERSION = 2


def action_descriptor(action: Mapping[str, Any]) -> dict[str, Any]:
    return {field: action.get(field) for field in (
        "kind", "card", "controller", "location", "sequence", "description",
    )}


def snapshot_observation(snapshot: Any, legal_indices: list[int]) -> dict[str, Any]:
    """Return a stable, JSON-compatible observation for a replay snapshot."""
    actions = snapshot.decision["actions"]
    return {
        "schema": "yapping.observation.v1",
        "zones": {name: list(cards) for name, cards in snapshot.zones.items()},
        "player": snapshot.decision["player"],
        "turn": snapshot.decision["turn"],
        "legal_action_indices": list(legal_indices),
        "legal_actions": [action_descriptor(actions[index]) for index in legal_indices],
        "action_history": list(snapshot.actions),
    }


def validate_example(row: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "observation", "state_key", "legal_actions",
        "oracle_action", "oracle_value", "oracle_action_values", "complete", "search_limits",
        "provenance",
    }
    missing = required.difference(row)
    if missing:
        raise ValueError(f"oracle example missing fields: {sorted(missing)}")
    if row["schema_version"] != ORACLE_SCHEMA_VERSION:
        raise ValueError(f"unsupported oracle schema: {row['schema_version']}")
    if not set(row["oracle_action_values"]).issubset(
        {str(index) for index in row["legal_actions"]}
    ):
        raise ValueError("oracle action values contain an illegal action")
