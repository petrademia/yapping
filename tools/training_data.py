"""Export and evaluate oracle-labelled policy/value datasets."""

from __future__ import annotations

import argparse
import contextlib
import gc
import io
import json
import time
from pathlib import Path

from analyze_ash import ReplayCursor
from analyze_consistency import sample_hands
from matchup_config import experiment_matchup, load_config
from search_opening import legal, run_search
from trace_albaz_combo import ROOT, SCRIPTS
from yapping import (
    ORACLE_SCHEMA_VERSION,
    report_provenance,
    snapshot_observation,
    validate_example,
)
from yapping._ocgcore import Duel
from yapping.hands import hand_id, trajectory_id, validate_hand_in_deck
from yapping.models import TabularPolicyValue
from yapping.oracle_dataset import audit_oracle_rows


def _rows_from_search(
    *,
    result,
    interruption: str,
    opening_hand,
    config,
    max_nodes: int,
    max_depth: int,
    adapter,
):
    matchup = experiment_matchup(config, opening_hand=opening_hand)
    card = config["interruptions"].get(interruption)
    cursor = ReplayCursor(
        card, list(opening_hand) if opening_hand is not None else None, 1,
        adapter, matchup,
    )
    cursor(())
    hid = hand_id(opening_hand) if opening_hand is not None else None
    tid = trajectory_id(
        hid or "default",
        interruption,
        max_nodes=max_nodes,
        max_depth=max_depth,
    )
    rows = []
    for depth, action in enumerate(result.actions):
        node = cursor(result.actions[:depth])
        legal_indices = list(legal(node, config))
        action_values = {
            str(index): value
            for index, value in result.action_values.items()
            if index in legal_indices
        }
        # Root minimax exposes a full legal table; deeper nodes keep the
        # chosen action's value only (do not fabricate sibling Q values).
        action_values.setdefault(str(action), result.score)
        provenance = report_provenance(
            database=ROOT / "assets/cards.cdb",
            scripts=SCRIPTS,
            max_nodes=max_nodes,
            max_depth=max_depth,
            complete=result.complete,
            revision_root=ROOT,
        )
        provenance.update({
            "hand_id": hid,
            "scenario_id": interruption,
            "trajectory_id": tid,
            "opening_hand": list(opening_hand) if opening_hand is not None else None,
            "visited_states": result.visited_states,
            "config_name": config.get("name"),
        })
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
            "scenario_id": interruption,
            "hand_id": hid,
            "trajectory_id": tid,
            "opening_hand": list(opening_hand) if opening_hand is not None else None,
            "search_limits": {"max_nodes": max_nodes, "max_depth": max_depth},
            "provenance": provenance,
        }
        validate_example(row)
        rows.append(row)
    return rows


def export(
    path,
    interruption="ash",
    max_nodes=100,
    max_depth=40,
    config=None,
    opening_hand=None,
):
    """Legacy single-hand export (default fixture hand when opening_hand is None)."""
    config = config or load_config()
    if opening_hand is not None:
        validate_hand_in_deck(config["main_deck"], opening_hand)
    with contextlib.redirect_stdout(io.StringIO()):
        result, _, config = run_search(
            interruption,
            max_nodes=max_nodes,
            max_depth=max_depth,
            opening_hand=opening_hand,
            config=config,
        )
    gc.collect()
    adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    try:
        rows = _rows_from_search(
            result=result,
            interruption=interruption,
            opening_hand=opening_hand,
            config=config,
            max_nodes=max_nodes,
            max_depth=max_depth,
            adapter=adapter,
        )
    finally:
        del adapter
        gc.collect()
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n")
    return len(rows)


def export_multi_hand(
    path,
    *,
    config,
    sample_hand_count: int,
    seed: int,
    interruptions: list[str],
    max_nodes: int,
    max_depth: int,
    complete_only: bool = True,
    incomplete_path=None,
    hands=None,
):
    """Export oracle examples across many opening hands × interruptions."""
    deck = config["main_deck"]
    sampled = list(hands) if hands is not None else list(
        sample_hands(deck, sample_hand_count, seed)
    )
    for hand in sampled:
        validate_hand_in_deck(deck, hand)

    adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    complete_rows = []
    incomplete_rows = []
    skips = []
    search_meta = []
    started = time.perf_counter()
    try:
        for hand in sampled:
            hid = hand_id(hand)
            for interruption in interruptions:
                print(
                    f"[export-multi] start hand={hid} scenario={interruption}",
                    flush=True,
                )
                search_started = time.perf_counter()
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        result, _, _ = run_search(
                            interruption,
                            max_nodes=max_nodes,
                            max_depth=max_depth,
                            opening_hand=list(hand),
                            config=config,
                            adapter=adapter,
                        )
                except Exception as error:  # noqa: BLE001 - record OCGCore/script failures
                    elapsed = time.perf_counter() - search_started
                    meta = {
                        "hand_id": hid,
                        "opening_hand": list(hand),
                        "scenario_id": interruption,
                        "complete": False,
                        "visited_states": None,
                        "score": None,
                        "runtime_seconds": elapsed,
                        "max_nodes": max_nodes,
                        "max_depth": max_depth,
                        "error": f"{type(error).__name__}: {error}",
                    }
                    search_meta.append(meta)
                    skips.append({**meta, "reason": "search_error"})
                    print(
                        f"[export-multi] hand={hid} scenario={interruption} "
                        f"ERROR sec={elapsed:.1f} {meta['error']}",
                        flush=True,
                    )
                    gc.collect()
                    continue
                elapsed = time.perf_counter() - search_started
                meta = {
                    "hand_id": hid,
                    "opening_hand": list(hand),
                    "scenario_id": interruption,
                    "complete": result.complete,
                    "visited_states": result.visited_states,
                    "score": result.score,
                    "runtime_seconds": elapsed,
                    "max_nodes": max_nodes,
                    "max_depth": max_depth,
                }
                search_meta.append(meta)
                rows = _rows_from_search(
                    result=result,
                    interruption=interruption,
                    opening_hand=hand,
                    config=config,
                    max_nodes=max_nodes,
                    max_depth=max_depth,
                    adapter=adapter,
                )
                print(
                    f"[export-multi] hand={hid} scenario={interruption} "
                    f"complete={result.complete} visited={result.visited_states} "
                    f"score={result.score} sec={elapsed:.1f} "
                    f"examples={len(rows)}",
                    flush=True,
                )
                if result.complete:
                    complete_rows.extend(rows)
                else:
                    incomplete_rows.extend(rows)
                    skips.append({
                        **meta,
                        "reason": "incomplete_search",
                        "examples_omitted_from_complete_set": len(rows),
                    })
                gc.collect()
    finally:
        del adapter
        gc.collect()

    total_runtime = time.perf_counter() - started
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    exported = complete_rows if complete_only else complete_rows + incomplete_rows
    output.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in exported) + "\n"
        if exported else ""
    )

    if incomplete_path and incomplete_rows:
        incomplete_out = Path(incomplete_path)
        incomplete_out.parent.mkdir(parents=True, exist_ok=True)
        incomplete_out.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in incomplete_rows) + "\n"
        )

    searched_hands = len(sampled)
    searched_scenarios = len(search_meta)
    complete_searches = sum(1 for item in search_meta if item["complete"])
    summary = {
        "config": config.get("name"),
        "seed": seed,
        "requested_hands": sample_hand_count,
        "searched_hands": searched_hands,
        "interruptions": interruptions,
        "searched_scenarios": searched_scenarios,
        "complete_searches": complete_searches,
        "incomplete_searches": searched_scenarios - complete_searches,
        "complete_only": complete_only,
        "complete_examples": len(complete_rows),
        "incomplete_examples": len(incomplete_rows),
        "exported_examples": len(exported),
        "total_runtime_seconds": total_runtime,
        "mean_runtime_per_hand": (
            total_runtime / searched_hands if searched_hands else 0.0
        ),
        "mean_runtime_per_search": (
            total_runtime / searched_scenarios if searched_scenarios else 0.0
        ),
        "examples_per_hand": (
            len(exported) / searched_hands if searched_hands else 0.0
        ),
        "complete_search_rate": (
            complete_searches / searched_scenarios if searched_scenarios else 0.0
        ),
        "skips": skips,
        "searches": search_meta,
        "output": str(output),
        "incomplete_output": str(incomplete_path) if incomplete_path else None,
        "audit": audit_oracle_rows(exported) if exported else audit_oracle_rows([]),
    }
    return summary


def evaluate(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line]
    split = max(1, len(rows) // 2)
    model = TabularPolicyValue().fit(rows[:split])
    holdout = rows[split:]
    agreement = sum(model.predict_action(row) == row["oracle_action"] for row in holdout)
    errors = [abs(model.predict_value(row) - row["oracle_value"]) for row in holdout]
    return {
        "examples": len(rows),
        "holdout_examples": len(holdout),
        "policy_agreement": agreement / len(holdout) if holdout else 0,
        "value_mae": sum(errors) / len(errors) if errors else 0,
        "complete_examples": sum(row["complete"] for row in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["export", "export-multi", "evaluate", "audit"])
    parser.add_argument("path", nargs="?", default="artifacts/training.jsonl")
    parser.add_argument("--config", default=None)
    parser.add_argument("--max-nodes", type=int, default=100)
    parser.add_argument("--max-depth", type=int, default=40)
    parser.add_argument("--interruption", default="ash")
    parser.add_argument("--interruptions", default="none,ash,impermanence")
    parser.add_argument("--sample-hands", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--complete-only", action="store_true", default=True)
    parser.add_argument("--include-incomplete", action="store_true")
    parser.add_argument("--incomplete-output", default=None)
    parser.add_argument("--summary-output", default=None)
    args = parser.parse_args()
    if args.command == "export":
        print(json.dumps({
            "examples": export(
                args.path,
                interruption=args.interruption,
                max_nodes=args.max_nodes,
                max_depth=args.max_depth,
                config=load_config(args.config),
            )
        }))
        return
    if args.command == "export-multi":
        if args.sample_hands <= 0:
            raise SystemExit("--sample-hands must be > 0 for export-multi")
        config = load_config(args.config)
        interruptions = [
            name.strip() for name in args.interruptions.split(",") if name.strip()
        ]
        incomplete_output = args.incomplete_output
        if incomplete_output is None and not args.include_incomplete:
            incomplete_output = str(Path(args.path).with_suffix("")) + "_incomplete.jsonl"
        summary = export_multi_hand(
            args.path,
            config=config,
            sample_hand_count=args.sample_hands,
            seed=args.seed,
            interruptions=interruptions,
            max_nodes=args.max_nodes,
            max_depth=args.max_depth,
            complete_only=not args.include_incomplete,
            incomplete_path=incomplete_output,
        )
        if args.summary_output:
            Path(args.summary_output).write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n"
            )
        print(json.dumps({
            "exported_examples": summary["exported_examples"],
            "complete_searches": summary["complete_searches"],
            "incomplete_searches": summary["incomplete_searches"],
            "total_runtime_seconds": summary["total_runtime_seconds"],
            "audit": summary["audit"],
            "summary_output": args.summary_output,
        }, indent=2, sort_keys=True))
        return
    if args.command == "audit":
        rows = [
            json.loads(line) for line in Path(args.path).read_text().splitlines() if line
        ]
        print(json.dumps(audit_oracle_rows(rows), indent=2, sort_keys=True))
        return
    print(json.dumps(evaluate(args.path), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
