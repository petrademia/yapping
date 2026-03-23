#!/usr/bin/env python3
"""
YAPPING — Yet Another Path Processor & Inference Node Generator

Entry point to start the combo analyzer.

  # Hand Simulator (draw 5, first 10 legal actions)
  python -m cli.cli hand-sim --deck data/decks/<your>.ydk

  # Future: combo best / all / surprise
  python -m cli.cli combo --deck ... --mode best|all|surprise
"""


def main() -> None:
    from cli import cli
    cli.main()


if __name__ == "__main__":
    main()
