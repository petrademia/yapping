#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain.search import search_combo_dfs, _reset_to_main_phase_idle
from brain.combo import load_recipe
from cli.hand_simulator import _load_card_id_to_code, _load_code_to_name
from engine.environment import create_env


def main() -> int:
    ygo_root = ROOT / "vendor" / "yapcore"
    recipe_path = ROOT / "data/combos/branded_opening_granguignol.json"
    recipe = load_recipe(recipe_path)
    deck_path = ROOT / recipe["deck"]

    cid_map = _load_card_id_to_code(ygo_root)
    name_map = _load_code_to_name(ROOT, ygo_root)

    env = create_env(deck_path=deck_path, ygo_env_root=ygo_root, seed=recipe.get("seed"))
    if not _reset_to_main_phase_idle(env, cid_map, name_map):
        raise RuntimeError("DFS regression failed: could not reach main phase idle.")

    result = search_combo_dfs(
        env,
        cid_map,
        name_map,
        max_depth=1,
        max_nodes=5,
        verbose=False,
        first_turn=True,
        lock_initial_player=True,
    )
    report = result.as_report_dict(cid_map, name_map)

    details = {
        "visited": result.visited,
        "best_score": result.best_score,
        "best_labels": result.best_labels,
        "best_prompt_labels": result.best_prompt_labels,
        "best_trace_len": len(result.best_trace),
    }
    expected_prompt_prefix = [
        "Summon Aluber the Jester of Despia",
        "Place → m1",
        "Yes (Aluber the Jester of Despia)",
        "Select Branded Retribution",
    ]
    if result.visited <= 1:
        raise RuntimeError("DFS regression failed:\n" + json.dumps(details, indent=2))
    if result.best_prompt_labels[:4] != expected_prompt_prefix:
        raise RuntimeError("DFS regression failed:\n" + json.dumps(details, indent=2))
    if "best_trace" not in report:
        raise RuntimeError("DFS regression failed: report missing best_trace.")

    print("Branded DFS regression passed.")
    print(f"Visited: {result.visited}")
    print(f"Best score: {result.best_score}")
    print(f"Best path length: {len(result.best_labels)}")
    print(f"Best trace length: {len(result.best_trace)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
