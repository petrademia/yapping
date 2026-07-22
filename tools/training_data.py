"""Export and evaluate a tiny oracle-labelled policy/value dataset."""

import argparse
import contextlib
import gc
import io
import json
from pathlib import Path

from analyze_ash import ReplayCursor, endboard_score
from matchup_config import load_config
from search_opening import legal, search
from trace_albaz_combo import ASH_BLOSSOM, ROOT, SCRIPTS
from yapping._ocgcore import Duel
from yapping import (ORACLE_SCHEMA_VERSION, report_provenance,
                     snapshot_observation, validate_example)
from yapping.models import TabularPolicyValue


def export(path, interruption="ash", max_nodes=100, max_depth=40, config=None):
    config = config or load_config()
    with contextlib.redirect_stdout(io.StringIO()):
        result, _ = search(interruption, max_nodes=max_nodes, max_depth=max_depth,
                           config=config)
    gc.collect()
    adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    cursor = ReplayCursor(config["interruptions"][interruption], None, 1,
                          adapter, config)
    # search leaves the cursor at its terminal path; restore the root before
    # walking the labelled trajectory.
    cursor(())
    rows = []
    for depth, action in enumerate(result.actions):
        node = cursor(result.actions[:depth])
        legal_indices = list(legal(node, config))
        action_values = {
            str(index): value for index, value in result.action_values.items()
            if index in legal_indices
        }
        # The complete root action table is available from minimax. For later
        # trajectory states, retain the oracle action's value explicitly.
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
                database=ROOT / "assets/cards.cdb", scripts=SCRIPTS,
                max_nodes=max_nodes, max_depth=max_depth,
                complete=result.complete, revision_root=ROOT,
            ),
        }
        validate_example(row)
        rows.append(row)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n")
    return len(rows)


def evaluate(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line]
    split = max(1, len(rows) // 2)
    model = TabularPolicyValue().fit(rows[:split])
    holdout = rows[split:]
    agreement = sum(model.predict_action(row) == row["oracle_action"] for row in holdout)
    errors = [abs(model.predict_value(row) - row["oracle_value"]) for row in holdout]
    return {"examples": len(rows), "holdout_examples": len(holdout),
            "policy_agreement": agreement / len(holdout) if holdout else 0,
            "value_mae": sum(errors) / len(errors) if errors else 0,
            "complete_examples": sum(row["complete"] for row in rows)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "evaluate"])
    parser.add_argument("path", default="artifacts/training.jsonl", nargs="?")
    parser.add_argument("--max-nodes", type=int, default=100)
    parser.add_argument("--max-depth", type=int, default=40)
    args = parser.parse_args()
    if args.command == "export":
        print(json.dumps({"examples": export(args.path, max_nodes=args.max_nodes,
                                               max_depth=args.max_depth)}))
    else:
        print(json.dumps(evaluate(args.path), indent=2, sort_keys=True))
