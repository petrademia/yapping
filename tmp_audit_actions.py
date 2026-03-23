#!/usr/bin/env python3
"""
Audit: which actions does the engine offer, and when?

Samples one or more initial states (and optionally after 1–2 steps), then reports:
- Counts by action type (Summon, MSet, Set, Activate, Place, Pass, etc.)
- Whether any "Activate" (act_id=8) actions appear
- Sample labels so we know exactly what the agent can choose from

Run from repo root (or with YGO_ENV_ROOT set):
  python tmp_audit_actions.py
  python tmp_audit_actions.py --seeds 5 --steps 2
  python tmp_audit_actions.py --target-code 73819701   # debug: hand with Fallen of the White Dragon, can it Activate?
"""
import argparse
import json
import os
import random
import sys
from pathlib import Path
from collections import defaultdict

_HERE = Path(__file__).resolve().parent
_YGO_ROOT = _HERE / "vendor" / "ygo-env"
_DECK = _YGO_ROOT / "assets" / "deck" / "Branded.ydk"

sys.path.insert(0, str(_HERE))

from engine.wrapper import YgoEnvWrapper
from engine.actions import decode_action_features

# ActionAct (match ygopro.h) for reporting
ACT_NAMES = [
    "None", "Set", "Repo", "SpSummon", "Summon", "MSet",
    "Attack", "DirectAttack", "Activate", "Cancel",
]


def load_card_id_to_code(ygo_root: Path) -> dict:
    path = ygo_root / "example" / "code_list.txt"
    out = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, start=1):
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                out[i] = int(parts[0])
    return out


def load_code_to_name(root: Path) -> dict:
    db = root / "data" / "card_code_to_name.json"
    if not db.exists():
        return {}
    with open(db, encoding="utf-8") as f:
        return json.load(f)


def get_all_actions(env, cid_map, name_map):
    """Return list of (idx, feat, label, act_id)."""
    legal = env.get_legal_actions()
    out = []
    for idx in legal:
        feat = env.action_features(idx)
        if feat and len(feat) >= 5:
            act_id = int(feat[4])
            label = decode_action_features(feat, cid_map, name_map)
        else:
            act_id = -1
            label = f"action_{idx}"
        out.append((idx, feat, label, act_id))
    return out


def audit_state(env, cid_map, name_map, state_label: str) -> dict:
    """Collect counts by act_id and by label prefix. Returns summary dict."""
    actions = get_all_actions(env, cid_map, name_map)
    by_act_id = defaultdict(int)
    by_prefix = defaultdict(int)
    activate_labels = []
    msg_to_id = 0

    for _idx, feat, label, act_id in actions:
        if feat is not None and len(feat) >= 4 and int(feat[3]) != 0 and msg_to_id == 0:
            msg_to_id = int(feat[3])
        by_act_id[act_id] += 1
        if act_id == 8:
            activate_labels.append(label)
        prefix = label.split()[0] if label else "?"
        by_prefix[prefix] += 1

    return {
        "state": state_label,
        "total": len(actions),
        "by_act_id": dict(by_act_id),
        "by_prefix": dict(by_prefix),
        "msg_to_id": msg_to_id,
        "activate_labels": activate_labels,
        "all_labels": [label for _, _, label, _ in actions],
        "all_labels_sample": [label for _, _, label, _ in actions[:25]],
    }


def print_report(report: dict):
    r = report
    print(f"\n  --- {r['state']} ---")
    print(f"  Total legal actions: {r['total']}")
    print("  By act_id:")
    for aid in sorted(r["by_act_id"].keys()):
        name = ACT_NAMES[aid] if 0 <= aid < len(ACT_NAMES) else f"act_{aid}"
        print(f"    {name}: {r['by_act_id'][aid]}")
    print("  By label prefix:")
    for prefix in sorted(r["by_prefix"].keys()):
        print(f"    {prefix}: {r['by_prefix'][prefix]}")
    if r["activate_labels"]:
        print("  Activate (act_id=8) labels:")
        for lbl in r["activate_labels"][:15]:
            print(f"    - {lbl}")
        if len(r["activate_labels"]) > 15:
            print(f"    ... and {len(r['activate_labels']) - 15} more")
    else:
        print("  Activate (act_id=8): (none)")
    if r["all_labels_sample"]:
        print("  Sample labels (first 15):")
        for lbl in r["all_labels_sample"][:15]:
            print(f"    - {lbl}")


# msg_to_id: 1 = select_idle (IDLECMD)
MSG_SELECT_IDLE = 1


def _is_idle_state(report: dict) -> bool:
    """True if Main Phase idle: select_idle (msg_to_id=1) with at least one Summon/MSet/Set/Activate.
    Works when hand has no summonable/setable cards (only Activate + Pass). Draw Phase idle has only Pass."""
    if report.get("msg_to_id", 0) != MSG_SELECT_IDLE:
        return False
    prefixes = set(report["by_prefix"].keys())
    return bool(prefixes & {"Summon", "MSet", "Set", "Activate"})


def _pass_or_cancel_action_index(env, cid_map, name_map) -> int | None:
    """Return the action index for Pass/Cancel (e.g. don't chain, end phase), or None."""
    actions = get_all_actions(env, cid_map, name_map)
    for idx, _feat, label, act_id in actions:
        if act_id == 9:  # Cancel
            return idx
        if "Pass" in label or "don't chain" in label.lower():
            return idx
    # Often the last option is Pass/Cancel
    if actions:
        return actions[-1][0]
    return None


def _try_reach_idle(env, cid_map, name_map, max_steps: int = 10) -> bool:
    """Take Pass/Cancel until we're in Main Phase idle or max_steps. Returns True if idle reached.
    May pass through Draw Phase (fewer options) before reaching Main Phase."""
    for _ in range(max_steps):
        report = audit_state(env, cid_map, name_map, "")
        if _is_idle_state(report):
            return True
        idx = _pass_or_cancel_action_index(env, cid_map, name_map)
        if idx is None:
            return False
        obs, term, trunc, _ = env.step(idx)
        if term or trunc:
            return False
    return False


def run_target_code_debug(env, cid_map, name_map, target_code: int, max_attempts: int = 300):
    """Find a hand containing target_code, reach Main Phase idle if needed (pass on chain), then audit."""
    target_name = name_map.get(str(target_code), f"code {target_code}")
    print(f"\nSearching for a hand containing {target_name} ({target_code}) (max {max_attempts} seeds)...")
    for attempt in range(max_attempts):
        seed = random.randint(1, 2**31 - 1)
        raw_obs, hand_ids, _ = env.reset(seed=seed)
        hand_codes = [cid_map.get(h, 0) for h in hand_ids]
        if target_code not in hand_codes:
            if (attempt + 1) % 50 == 0:
                print(f"  ... {attempt + 1} attempts")
            continue
        report = audit_state(env, cid_map, name_map, f"State — hand contains {target_name} (seed={seed})")
        if not _is_idle_state(report):
            # Chain or other prompt — try to reach Main Phase idle by passing (Pass / don't chain, etc.)
            if not _try_reach_idle(env, cid_map, name_map):
                continue
            report = audit_state(env, cid_map, name_map, f"After passing to idle — hand contains {target_name} (seed={seed})")
            print(f"  Found at seed={seed} (attempt {attempt + 1}); passed chain window to reach Main Phase idle.")
        else:
            print(f"  Found at seed={seed} (attempt {attempt + 1})")
        # We're in idle (either was already or we passed to get here)
        hand_names_list = [name_map.get(str(c), str(c)) for c in hand_codes]
        print(f"  Hand: {hand_names_list}")
        print_report(report)
        # Check explicitly for Activate targeting this card
        labels_for_target = [lbl for lbl in report["all_labels"] if target_name in lbl or "White Dragon" in lbl or str(target_code) in lbl]
        activate_for_target = [lbl for lbl in report["activate_labels"] if target_name in lbl or "White Dragon" in lbl]
        print("\n  " + "=" * 56)
        print(f"  TARGET CARD: {target_name} ({target_code})")
        print("  " + "=" * 56)
        print(f"  In hand: Yes")
        print(f"  Legal actions mentioning this card: {len(labels_for_target)}")
        for lbl in labels_for_target:
            print(f"    - {lbl}")
        if activate_for_target:
            print(f"  'Activate {target_name}' in legal list: Yes")
        else:
            print(f"  'Activate {target_name}' in legal list: No")
        print()
        return
    print(f"  Could not draw {target_name} in {max_attempts} attempts.")
    print()


def main():
    ap = argparse.ArgumentParser(description="Audit which actions the engine offers.")
    ap.add_argument("--seeds", type=int, default=3, help="Number of initial states to sample (default 3)")
    ap.add_argument("--steps", type=int, default=1, help="After initial, take this many steps and audit again (default 1)")
    ap.add_argument("--deck", type=Path, default=_DECK, help="Path to .ydk deck")
    ap.add_argument("--target-code", type=int, default=None, help="Debug: find hand containing this card (e.g. 73819701) and report if Activate appears for it")
    args = ap.parse_args()

    if not _YGO_ROOT.is_dir():
        print("vendor/ygo-env not found. Run from repo root.", file=sys.stderr)
        sys.exit(1)

    # Resolve deck path (default _DECK is under _HERE)
    deck_path = (args.deck if args.deck.is_absolute() else _HERE / args.deck).resolve()
    if not deck_path.is_file():
        print(f"Deck not found: {deck_path}", file=sys.stderr)
        sys.exit(1)
    # Engine expects cwd to be ygo-env (for ./script/). Run from repo root: python tmp_audit_actions.py
    os.chdir(_YGO_ROOT)

    print("Loading card data...", flush=True)
    cid_map = load_card_id_to_code(_YGO_ROOT)
    name_map = load_code_to_name(_HERE)
    # One env per run; we reuse it for all seeds / target-code attempts (reset(seed=...) only).
    print("Creating env (once per run)...", flush=True)
    env = YgoEnvWrapper(deck_path=deck_path, ygo_env_root=_YGO_ROOT, seed=None)

    if args.target_code is not None:
        run_target_code_debug(env, cid_map, name_map, args.target_code)
        return

    all_reports = []

    for run in range(args.seeds):
        seed = run + 1
        env.reset(seed=seed)
        report = audit_state(env, cid_map, name_map, f"Initial state (seed={seed})")
        all_reports.append(report)
        print_report(report)

        for step in range(args.steps):
            actions = get_all_actions(env, cid_map, name_map)
            if not actions:
                print(f"\n  (No actions after step {step + 1}; stopping.)")
                break
            # Take first legal action
            idx = actions[0][0]
            env.step(idx)
            report = audit_state(env, cid_map, name_map, f"After step {step + 1} (seed={seed})")
            all_reports.append(report)
            print_report(report)

    # Summary across all
    print("\n" + "=" * 60)
    print("  SUMMARY (what the agent can choose from)")
    print("=" * 60)
    any_activate = any(r["activate_labels"] for r in all_reports)
    print(f"  Activate (act_id=8) seen in any state: {'Yes' if any_activate else 'No'}")
    act_ids_seen = set()
    for r in all_reports:
        act_ids_seen.update(r["by_act_id"].keys())
    print(f"  Action types (act_id) seen: {sorted(act_ids_seen)}")
    prefixes_seen = set()
    for r in all_reports:
        prefixes_seen.update(r["by_prefix"].keys())
    print(f"  Label prefixes seen: {sorted(prefixes_seen)}")
    print()


if __name__ == "__main__":
    main()
