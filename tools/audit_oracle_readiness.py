"""Export and audit oracle-labelled examples for Level-6 readiness."""

from __future__ import annotations

import argparse
import contextlib
import gc
import io
import json
from collections import Counter
from pathlib import Path

from analyze_ash import ReplayCursor
from matchup_config import load_config
from search_opening import legal, search
from trace_albaz_combo import ROOT, SCRIPTS
from training_data import evaluate
from yapping import (
    ORACLE_SCHEMA_VERSION,
    report_provenance,
    snapshot_observation,
    validate_example,
)
from yapping._ocgcore import Duel


ROOT_DIR = Path(__file__).parents[1]


def export_interruption(path: Path, interruption: str, max_nodes: int, max_depth: int, config):
    with contextlib.redirect_stdout(io.StringIO()):
        result, _ = search(
            interruption, max_nodes=max_nodes, max_depth=max_depth, config=config
        )
    gc.collect()
    card = config["interruptions"].get(interruption)
    adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    cursor = ReplayCursor(card, None, 1, adapter, None)
    cursor(())
    rows = []
    try:
        for depth, action in enumerate(result.actions):
            node = cursor(result.actions[:depth])
            legal_indices = list(legal(node, config))
            action_values = {
                str(index): value
                for index, value in result.action_values.items()
                if index in legal_indices
            }
            action_values.setdefault(str(action), result.score)
            row = {
                "schema_version": ORACLE_SCHEMA_VERSION,
                "state_key": node.key.hex(),
                "observation": snapshot_observation(node, legal_indices),
                "legal_actions": legal_indices,
                "oracle_action": action,
                "oracle_value": result.score,
                "oracle_action_values": action_values,
                "complete": result.complete,
                "depth": depth,
                "interruption": interruption,
                "search_limits": {"max_nodes": max_nodes, "max_depth": max_depth},
                "provenance": report_provenance(
                    database=ROOT / "assets/cards.cdb",
                    scripts=SCRIPTS,
                    max_nodes=max_nodes,
                    max_depth=max_depth,
                    complete=result.complete,
                    revision_root=ROOT_DIR,
                ),
            }
            validate_example(row)
            rows.append(row)
    finally:
        del adapter
        gc.collect()
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n")
    return rows


def audit_rows(rows, path: Path | None = None) -> dict:
    for row in rows:
        validate_example(row)
    unique_states = {row["state_key"] for row in rows}
    depths = Counter(int(row.get("depth", -1)) for row in rows)
    interruptions = Counter(row.get("interruption") for row in rows)
    complete_count = sum(bool(row["complete"]) for row in rows)
    root = [row for row in rows if int(row.get("depth", -1)) == 0]
    trajectory = [row for row in rows if int(row.get("depth", -1)) > 0]

    def coverage(row):
        legal_set = {str(index) for index in row["legal_actions"]}
        labelled = set(row["oracle_action_values"])
        return {
            "full_legal_coverage": labelled == legal_set,
            "chosen_only": labelled == {str(row["oracle_action"])},
        }

    coverages = [coverage(row) for row in rows]
    descriptors = Counter()
    for row in rows:
        legal_actions = row["observation"].get("legal_actions") or []
        indices = row["observation"].get("legal_action_indices") or row["legal_actions"]
        if row["oracle_action"] in indices:
            position = list(indices).index(row["oracle_action"])
            if position < len(legal_actions):
                descriptors[legal_actions[position].get("kind", "?")] += 1

    result = {
        "path": str(path) if path else None,
        "total_examples": len(rows),
        "unique_state_keys": len(unique_states),
        "duplicate_state_rows": len(rows) - len(unique_states),
        "root_examples": len(root),
        "trajectory_examples": len(trajectory),
        "complete_examples": complete_count,
        "incomplete_search_examples": len(rows) - complete_count,
        "examples_with_full_action_value_labels": sum(
            item["full_legal_coverage"] for item in coverages
        ),
        "examples_with_chosen_action_only_labels": sum(
            item["chosen_only"] for item in coverages
        ),
        "root_full_action_value_labels": sum(
            coverage(row)["full_legal_coverage"] for row in root
        ),
        "trajectory_full_action_value_labels": sum(
            coverage(row)["full_legal_coverage"] for row in trajectory
        ),
        "depth_distribution": dict(sorted(depths.items())),
        "interruption_distribution": dict(interruptions),
        "oracle_action_index_distribution": dict(
            Counter(str(row["oracle_action"]) for row in rows)
        ),
        "oracle_action_kind_distribution": dict(descriptors),
        "note": (
            "Full action-value tables are expected mainly at depth 0 from "
            "minimax root_action_values; deeper states typically label only "
            "the chosen action."
        ),
    }
    if path is not None and path.exists() and rows:
        result["tabular_plumbing_check"] = evaluate(path)
        result["tabular_plumbing_note"] = (
            "TabularPolicyValue can memorize state keys; not Level-7 generalization."
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(ROOT_DIR / "reports/data/oracle"))
    parser.add_argument("--max-nodes", type=int, default=50_000)
    parser.add_argument("--max-depth", type=int, default=180)
    parser.add_argument("--interruptions", default="none,ash,impermanence")
    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    config = load_config()
    exports = []
    all_rows = []
    for interruption in [name.strip() for name in args.interruptions.split(",") if name.strip()]:
        path = out_dir / f"oracle_{interruption}.jsonl"
        rows = export_interruption(
            path, interruption, args.max_nodes, args.max_depth, config
        )
        audit = audit_rows(rows, path)
        exports.append(audit)
        all_rows.extend(rows)
    combined_path = out_dir / "oracle_examples.jsonl"
    combined_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in all_rows) + "\n"
    )
    payload = {
        "exports": exports,
        "combined": audit_rows(all_rows, combined_path),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
