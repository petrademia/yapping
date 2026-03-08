"""
Command-line tool to run simulations.

Usage:
  # Hand Simulator (raw data: draw 5, first 10 legal actions)
  YGO_ENV_ROOT=/path/to/ygo-env python -m mouth.cli hand-sim --deck scripture/decks/MyDeck.ydk

  # Future: best path, full combo map, export
  python -m mouth.cli combo --deck ... --mode best|all|surprise
  python -m mouth.cli combo --deck ... --export json|flowchart --out combo.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YAPPING — combo path analyzer (Hand Simulator + Combo Map).",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # ---- hand-sim: draw 5, list first N legal actions ----
    hand_sim = subparsers.add_parser("hand-sim", help="Hand Simulator: draw 5, show first N legal actions (raw data).")
    hand_sim.add_argument("--deck", type=Path, required=True, help="Path to .ydk deck file")
    hand_sim.add_argument("--num-draw", type=int, default=5, help="Hand size (default: 5)")
    hand_sim.add_argument("--max-actions", type=int, default=10, help="Max legal actions to print (default: 10)")
    hand_sim.add_argument(
        "--ygo-env",
        type=Path,
        default=None,
        help="Root of ygo-env clone (default: env YGO_ENV_ROOT)",
    )
    hand_sim.add_argument("--seed", type=int, default=None, help="RNG seed for reproducible hand")

    # ---- combo (future): best / all / surprise ----
    combo = subparsers.add_parser("combo", help="Combo search: best path, full map, or surprise (future).")
    combo.add_argument("--deck", type=Path, required=True, help="Path to .ydk deck file")
    combo.add_argument(
        "--mode",
        choices=("best", "all", "surprise"),
        default="best",
        help="A=best board, B=everywhere hand can go, C=surprise (default: best)",
    )
    combo.add_argument("--export", choices=("json", "flowchart"), help="Export format")
    combo.add_argument("--out", type=Path, help="Output file path")
    combo.add_argument("--depth", type=int, default=None, help="Max search depth (future)")
    combo.add_argument("--max-branches", type=int, default=None, help="Max branches to explore (future)")

    args = parser.parse_args()

    if args.command == "hand-sim":
        from mouth.hand_simulator import run as hand_sim_run

        hand_sim_run(
            deck=args.deck,
            num_draw=args.num_draw,
            max_actions=args.max_actions,
            ygo_env_root=args.ygo_env,
            seed=args.seed,
        )
        return

    if args.command == "combo":
        print("Combo search (best/all/surprise) not yet implemented. Use hand-sim to see raw engine data.")
        print("  python -m mouth.cli hand-sim --deck scripture/decks/YourDeck.ydk")
        return

    parser.print_help()
    return


if __name__ == "__main__":
    main()
