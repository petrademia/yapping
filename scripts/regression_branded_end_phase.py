#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cli.hand_simulator import _load_card_id_to_code, _load_code_to_name
from engine.actions import decode_action_features
from engine.environment import create_env


def labels(env, cid_map, name_map):
    out = []
    for idx in env.get_legal_actions():
        feat = env.action_features(idx)
        label = decode_action_features(feat, cid_map, name_map) if feat is not None else f"action_{idx}"
        out.append((idx, label))
    return out


def pick(env, cid_map, name_map, needle, nth=0):
    opts = labels(env, cid_map, name_map)
    matches = [(idx, label) for idx, label in opts if needle.lower() in label.lower()]
    if len(matches) <= nth:
        dump = "\n".join(f"{idx}: {label}" for idx, label in opts)
        raise RuntimeError(f"Could not find action {needle!r} nth={nth}\n{dump}")
    env.step(matches[nth][0])


def main() -> int:
    ygo_root = ROOT / "vendor" / "ygopro-adapter"
    if not ygo_root.exists():
        legacy = ROOT / "vendor" / "ygo-env"
        ygo_root = legacy
    deck_path = ROOT / "data/decks/Branded.ydk"
    cid_map = _load_card_id_to_code(ygo_root)
    name_map = _load_code_to_name(ROOT, ygo_root)

    env = create_env(deck_path, ygo_root, seed=18)
    env.reset(seed=18)

    steps = [
        ("Activate Branded Fusion", 0),
        ("s1", 0),
        ("Select Albion the Branded Dragon", 0),
        ("Fallen of the White Dragon", 0),
        ("Blazing Cartesia", 0),
        ("m1", 0),
        ("face-up ATK", 0),
        ("Yes", 0),
        ("Granguignol", 0),
        ("Blazing Cartesia", 0),
        ("Fallen of the White Dragon", 0),
        ("m3", 0),
        ("face-up ATK", 0),
        ("Yes", 0),
        ("Albion the Shrouded Dragon", 0),
        ("Activate Albion the Shrouded Dragon (effect 2)", 0),
        ("Branded Sword", 0),
        ("Chain Branded Sword", 0),
        ("Fallen of the White Dragon", 0),
        ("m2", 0),
        ("face-up ATK", 0),
        ("Activate Fallen of the White Dragon", 0),
        ("The Dragon that Devours the Dogma", 0),
        ("m4", 0),
        ("face-up ATK", 0),
        ("Yes", 0),
        ("Incredible Ecclesia", 0),
        ("face-up ATK", 0),
        ("Fallen of the White Dragon", 0),
        ("face-up ATK", 0),
        ("SpSummon Alba-Lenatus", 0),
        ("Albion the Branded Dragon", 0),
        ("Fallen of the White Dragon", 0),
        ("Confirm selection", 0),
        ("m1", 0),
        ("face-up ATK", 0),
        ("Pass", 0),
        ("Chain The Dragon that Devours the Dogma", 0),
    ]

    for needle, nth in steps:
        pick(env, cid_map, name_map, needle, nth)

    final_labels = [label for _, label in labels(env, cid_map, name_map)]
    required = [
        "Select Tri-Brigade Mercourier",
        "Select The Fallen & The Virtuous",
    ]
    missing = [label for label in required if label not in final_labels]
    if missing:
        dump = "\n".join(final_labels)
        raise RuntimeError("Missing expected end-phase actions:\n" + "\n".join(missing) + "\n\nSaw:\n" + dump)

    print("Branded end-phase regression passed.")
    for label in final_labels:
        print(label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
