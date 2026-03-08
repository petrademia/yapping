"""
Hand Simulator — raw data from the engine.

Takes a deck, shuffles and draws 5, then lists the first N legal actions.
Use this to see the "raw" interface before building the full combo map.

Usage:
  export YGO_ENV_ROOT=/path/to/ygo-env
  cd /path/to/ygo-env   # so Lua scripts are found
  python -m mouth.hand_simulator --deck /path/to/yapping/scripture/decks/MyDeck.ydk

  Or from yapping repo with deck path:
  YGO_ENV_ROOT=/path/to/ygo-env python -m mouth.hand_simulator --deck scripture/decks/MyDeck.ydk
  (Run from ygo-env dir if the engine looks for scripts in cwd.)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="YAPPING Hand Simulator — draw 5, list first N legal actions (raw engine data)."
    )
    parser.add_argument(
        "--deck",
        type=Path,
        required=True,
        help="Path to .ydk deck file (e.g. scripture/decks/MyDeck.ydk)",
    )
    parser.add_argument(
        "--num-draw",
        type=int,
        default=5,
        help="Number of cards to treat as hand (default: 5). Engine may fix this.",
    )
    parser.add_argument(
        "--max-actions",
        type=int,
        default=10,
        help="Show at most this many legal actions (default: 10).",
    )
    parser.add_argument(
        "--ygo-env",
        type=Path,
        default=os.environ.get("YGO_ENV_ROOT"),
        help="Root of izzak98/ygo-env clone (default: env YGO_ENV_ROOT).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed for reproducible hand.",
    )
    return parser.parse_args()


def run(
    deck: Path,
    num_draw: int = 5,
    max_actions: int = 10,
    ygo_env_root: Path | None = None,
    seed: int | None = None,
) -> None:
    """Run the Hand Simulator with the given options (no argparse)."""
    deck_path = Path(deck).resolve()
    if not deck_path.is_file():
        print(f"Deck file not found: {deck_path}", file=sys.stderr)
        sys.exit(1)

    ygo_root = Path(ygo_env_root).resolve() if ygo_env_root else None
    if not ygo_root or not ygo_root.is_dir():
        ygo_root = os.environ.get("YGO_ENV_ROOT")
        ygo_root = Path(ygo_root).resolve() if ygo_root else None
    if not ygo_root or not ygo_root.is_dir():
        print(
            "YGO_ENV_ROOT not set or not a directory. Clone and build izzak98/ygo-env, then:\n"
            "  export YGO_ENV_ROOT=/path/to/ygo-env\n"
            "  cd $YGO_ENV_ROOT   # so Lua scripts are found\n"
            "  python -m mouth.hand_simulator --deck /path/to/scripture/decks/YourDeck.ydk\n"
            "See docs/ENGINE_SETUP.md",
            file=sys.stderr,
        )
        sys.exit(1)

    script_dir = Path(__file__).resolve().parent
    yapping_root = script_dir.parent
    if str(yapping_root) not in sys.path:
        sys.path.insert(0, str(yapping_root))

    try:
        from vocal_chords.environment import create_env
        from vocal_chords.actions import action_index_to_label
    except ImportError as e:
        print(f"Import error: {e}", file=sys.stderr)
        print("Run from the yapping repo or set PYTHONPATH to the yapping root.", file=sys.stderr)
        sys.exit(1)

    try:
        env = create_env(
            deck_path=deck_path,
            ygo_env_root=ygo_root,
            seed=seed,
        )
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    obs, hand, legal_actions = env.reset()

    print("--- YAPPING Hand Simulator (raw data) ---")
    print(f"Deck: {deck_path}")
    print(f"Hand (first {num_draw}): {hand[:num_draw]}")
    print()

    n = min(max_actions, len(legal_actions))
    print(f"First {n} legal actions (of {len(legal_actions)} total):")
    for i, idx in enumerate(legal_actions[:n], 1):
        print(f"  {i}. {action_index_to_label(idx)} (index {idx})")
    if len(legal_actions) > n:
        print(f"  ... and {len(legal_actions) - n} more.")
    print()
    print("Use this as the baseline before building the full combo map (Path B) or best-path (Path A).")


def main() -> None:
    args = _parse_args()

    run(
        deck=args.deck,
        num_draw=args.num_draw,
        max_actions=args.max_actions,
        ygo_env_root=args.ygo_env,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
