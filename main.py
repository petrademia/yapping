#!/usr/bin/env python3
"""
YAPPING — Yet Another Path Processor & Inference Node Generator

Entry point to start the combo analyzer.

  # Hand Simulator (draw 5, first 10 legal actions)
  python -m mouth.cli hand-sim --deck scripture/decks/<your>.ydk

  # Future: combo best / all / surprise
  python -m mouth.cli combo --deck ... --mode best|all|surprise
"""


def main() -> None:
    from mouth import cli
    cli.main()


if __name__ == "__main__":
    main()
