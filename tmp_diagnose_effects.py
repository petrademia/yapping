#!/usr/bin/env python3
"""
Diagnostic: force a hand containing Fallen of the White Dragon (73819701)
and inspect every legal action the engine offers.

Run: python tmp_diagnose_effects.py   (or ./tmp_diagnose_effects.py from repo root)
"""
import json
import random
import sys
from pathlib import Path

import numpy as np

_HERE     = Path(__file__).resolve().parent
_YGO_ROOT = _HERE / "vendor" / "ygo-env"
_DECK     = _YGO_ROOT / "assets" / "deck" / "Branded.ydk"

sys.path.insert(0, str(_HERE))

from engine.wrapper import YgoEnvWrapper
from engine.actions import decode_action_features


TARGET_CODE = 73819701   # Fallen of the White Dragon


def load_card_id_to_code(ygo_root: Path) -> dict:
    path = ygo_root / "example" / "code_list.txt"
    out = {}
    with open(path) as f:
        for i, line in enumerate(f, start=1):
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                out[i] = int(parts[0])
    return out


def load_code_to_name(root: Path) -> dict:
    db = root / "data" / "card_code_to_name.json"
    if not db.exists():
        return {}
    with open(db) as f:
        return json.load(f)


def hand_names(obs, cid_map, name_map):
    """Return (cid, code, name) tuples for cards in hand."""
    if not hasattr(obs, "get"):
        return []
    cards = obs.get("obs:cards_") or obs.get("cards_")
    if cards is None:
        return []
    arr = np.asarray(cards, dtype=np.uint8)
    if arr.ndim == 3:
        arr = arr[0]
    result = []
    for row in arr:
        if int(row[4]) != 0:   # controller 0 = us
            continue
        if int(row[2]) != 2:   # loc 2 = HAND
            continue
        cid  = int(row[0]) * 256 + int(row[1])
        code = cid_map.get(cid, 0)
        name = name_map.get(str(code), f"#{code}")
        result.append((cid, code, name))
    return result


def actions_snapshot(env, cid_map, name_map):
    """Decode all legal actions at current state."""
    legal = env.get_legal_actions()
    rows  = []
    for idx in legal:
        feat  = env.action_features(idx)
        label = decode_action_features(feat, cid_map, name_map) if feat else f"action_{idx}"
        rows.append((idx, feat, label))
    return rows


def print_state(label, hand, actions):
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"{'─'*60}")
    print("  Hand:")
    for cid, code, name in hand:
        marker = "  ◄ TARGET" if code == TARGET_CODE else ""
        print(f"    [{cid:4d}]  {code}  {name}{marker}")
    print(f"  Legal actions ({len(actions)}):")
    for idx, feat, label in actions:
        # Highlight Fallen-related actions
        hi = "  ★" if "White Dragon" in label or "Fallen" in label else ""
        print(f"    {idx:2d}. {label}{hi}")


def main():
    print("Loading card data...", flush=True)
    cid_map  = load_card_id_to_code(_YGO_ROOT)
    name_map = load_code_to_name(_HERE)
    # Reverse map: code → cid (for hand checking)
    code_to_cid = {v: k for k, v in cid_map.items()}
    target_cid  = code_to_cid.get(TARGET_CODE, None)
    print(f"  card_id for {TARGET_CODE} = {target_cid}")

    print("\nSearching for a hand containing Fallen of the White Dragon...")
    found_seed = None
    env        = None

    # Try seeds until we get Fallen of the White Dragon in hand
    for attempt in range(200):
        seed = random.randint(1, 2**31 - 1)
        e    = YgoEnvWrapper(deck_path=_DECK, ygo_env_root=_YGO_ROOT, seed=seed)
        raw_obs, hand_ids, legal = e.reset()
        # raw_obs is batched; get env-0
        obs = raw_obs[0] if hasattr(raw_obs, "__getitem__") and not hasattr(raw_obs, "get") else raw_obs
        if hasattr(raw_obs, "get"):
            obs = raw_obs

        hand_info = hand_names(obs, cid_map, name_map)
        hand_codes = [c for _, c, _ in hand_info]
        if TARGET_CODE in hand_codes:
            found_seed = seed
            env        = e
            break
        if attempt % 20 == 19:
            print(f"  ... {attempt+1} seeds tried, no match yet")

    if env is None:
        print("  Could not draw Fallen of the White Dragon in 200 attempts.")
        print("  Showing last hand for reference:")
        print_state("Last hand", hand_info, actions_snapshot(e, cid_map, name_map))
        return

    print(f"  Found!  seed={found_seed}  (attempt {attempt+1})")

    # --- Initial state ---
    raw_obs, _, _  = env.reset(seed=found_seed)
    obs = raw_obs
    hand_info      = hand_names(obs, cid_map, name_map)
    actions_init   = actions_snapshot(env, cid_map, name_map)
    print_state("INITIAL STATE (Main Phase 1)", hand_info, actions_init)

    # --- Investigate: when do "Activate" and "Branded Opening" appear? ---
    ACT_ACTIVATE = 8  # ActionAct::Activate in ygopro.h
    activate_actions = [(idx, lbl) for idx, feat, lbl in actions_init if feat and len(feat) > 4 and int(feat[4]) == ACT_ACTIVATE]
    branded_actions  = [(idx, lbl) for idx, feat, lbl in actions_init if feat and "Branded Opening" in lbl]
    print("\n  --- Activate (act_id=8) actions at initial state ---")
    if activate_actions:
        for idx, lbl in activate_actions:
            print(f"    [{idx}] {lbl}")
    else:
        print("    (none)")
    print("  --- Actions mentioning Branded Opening ---")
    if branded_actions:
        for idx, lbl in branded_actions:
            print(f"    [{idx}] {lbl}")
    else:
        print("    (none)")
    print("\n  Note: The Lua script (c73819701.lua) has EFFECT_TYPE_IGNITION + LOCATION_HAND,")
    print("  so Fallen of the White Dragon is designed to be activatable from hand. If no")
    print("  'Activate' appears, the engine (C++) may not be exposing ignition-from-hand in")
    print("  the idle command list. See docs/EFFECTS_AND_ACTIONS.md.")

    # --- Summon Fallen of the White Dragon, then re-list (expect Activate ignition) ---
    summon_white = None
    for idx, feat, lbl in actions_init:
        if "Summon" in lbl and "Fallen of the White Dragon" in lbl:
            summon_white = idx
            break
    if summon_white is not None:
        print("\n\n  Taking action: Summon Fallen of the White Dragon  (to see Activate ignition next)")
        raw_obs, _, _ = env.reset(seed=found_seed)
        obs = raw_obs
        obs, term, trunc, info = env.step(summon_white)
        hand_info  = hand_names(obs, cid_map, name_map)
        actions_after = actions_snapshot(env, cid_map, name_map)
        print_state("AFTER Summon Fallen of the White Dragon (look for 'Activate Fallen of the White Dragon')",
                    hand_info, actions_after)
        activate_now = [(idx, lbl) for idx, feat, lbl in actions_after if feat and len(feat) > 4 and int(feat[4]) == ACT_ACTIVATE and "White Dragon" in lbl]
        if activate_now:
            print("\n  ✓ Activate Fallen of the White Dragon (ignition) is now in the legal list.")
        else:
            print("\n  ? No 'Activate Fallen of the White Dragon' in this state (engine may use different msg/act).")
    else:
        print("\n  (Summon Fallen of the White Dragon not in initial list; skipping ignition check.)")

    # --- Step through first few actions (original behaviour) ---
    raw_obs, _, _ = env.reset(seed=found_seed)
    obs = raw_obs
    hand_info    = hand_names(obs, cid_map, name_map)
    actions_init = actions_snapshot(env, cid_map, name_map)
    print("\n\nStepping through first 3 actions to see how actions evolve:")
    for step_n in range(3):
        if not actions_init:
            print("  No actions left.")
            break
        action_to_take = actions_init[0][0]
        label_taken    = actions_init[0][2]
        obs, term, trunc, info = env.step(action_to_take)
        hand_info    = hand_names(obs, cid_map, name_map)
        actions_init = actions_snapshot(env, cid_map, name_map)
        print_state(f"After step {step_n+1}: took [{action_to_take}] '{label_taken}'",
                    hand_info, actions_init)
        if term or trunc:
            print("  Game ended.")
            break


if __name__ == "__main__":
    main()
