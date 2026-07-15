"""Opt-in production-depth cursor/oracle output regression."""

import argparse
import subprocess
import sys


def run(mode, interruption, nodes, depth):
    return subprocess.run(
        [sys.executable, "tools/search_opening.py", interruption,
         "--max-nodes", str(nodes), "--max-depth", str(depth),
         "--replay-mode", mode], capture_output=True, text=True, check=True,
    ).stdout


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("interruption", default="ghost_ogre", nargs="?")
    parser.add_argument("--max-nodes", type=int, default=22756)
    parser.add_argument("--max-depth", type=int, default=180)
    args = parser.parse_args()
    cursor = run("cursor", args.interruption, args.max_nodes, args.max_depth)
    oracle = run("oracle", args.interruption, args.max_nodes, args.max_depth)
    fields = ("score:", "provisional score", "complete:", "actions:",
              "end board:", "score breakdown:")
    left = [line for line in cursor.splitlines() if line.startswith(fields)]
    right = [line for line in oracle.splitlines() if line.startswith(fields)]
    if left != right:
        raise SystemExit("cursor/oracle output diverged")
    print(f"equivalent: True ({args.interruption}, {args.max_nodes} nodes)")
