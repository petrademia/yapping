#!/usr/bin/env python3
"""
Append card codes from a .ydk deck to the engine example/code_list.txt.
Used by setup/run scripts so that after a fresh clone the default deck's
codes are in the list (no "Card not found"). Stdlib only.
"""
from __future__ import annotations

import sys
from pathlib import Path


def deck_codes(deck_path: Path) -> set[int]:
    codes: set[int] = set()
    with open(deck_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip().strip("\r")
            if not line or line.startswith("#"):
                continue
            if line.isdigit():
                codes.add(int(line))
    return codes


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: append_deck_codes_to_code_list.py <deck.ydk> <code_list.txt> <scripts/script dir>", file=sys.stderr)
        sys.exit(1)
    deck_path = Path(sys.argv[1])
    code_list_path = Path(sys.argv[2])
    script_dir = Path(sys.argv[3])

    if not deck_path.is_file():
        print(f"Deck not found: {deck_path}", file=sys.stderr)
        sys.exit(1)
    if not code_list_path.is_file():
        print(f"code_list.txt not found: {code_list_path}", file=sys.stderr)
        sys.exit(1)

    codes = deck_codes(deck_path)
    existing: set[int] = set()
    with open(code_list_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                existing.add(int(parts[0]))
    missing = sorted(codes - existing)
    if not missing:
        print("All deck codes already in code_list. Nothing to append.")
        return
    with open(code_list_path, "a", encoding="utf-8") as f:
        for code in missing:
            has_script = 1 if (script_dir / f"c{code}.lua").is_file() else 0
            f.write(f"{code} {has_script}\n")
    print(f"Appended {len(missing)} card codes to {code_list_path}")


if __name__ == "__main__":
    main()
