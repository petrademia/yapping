#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain.combo import load_recipe, validate_recipe_replay
from cli.hand_simulator import _load_card_id_to_code, _load_code_to_name
from engine.environment import create_env


def main() -> int:
    ygo_root = ROOT / "vendor" / "yapcore"
    recipe_path = ROOT / "data/combos/branded_end_phase_to_alba_lenatus.json"
    recipe = load_recipe(recipe_path)
    deck_path = ROOT / recipe["deck"]

    cid_map = _load_card_id_to_code(ygo_root)
    name_map = _load_code_to_name(ROOT, ygo_root)

    env = create_env(deck_path=deck_path, ygo_env_root=ygo_root, seed=recipe.get("seed"))
    validation = validate_recipe_replay(recipe, env, cid_map, name_map)
    if not validation.success:
        details = {
            "combo_success": validation.result.success,
            "combo_error": validation.result.error,
            "replay_ok": validation.replay_ok,
            "replay_reason": validation.replay_reason,
            "replay_step": validation.replay_step,
            "trace_len": len(validation.trace),
        }
        raise RuntimeError("Branded end-phase recipe replay regression failed:\n" + json.dumps(details, indent=2))

    print("Branded end-phase recipe replay regression passed.")
    print(f"Trace length: {len(validation.trace)}")
    print(f"Steps: {len(recipe.get('steps', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
