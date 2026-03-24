#!/usr/bin/env python3
"""
Compare multiple engine transcript JSON files for reproducibility.

Usage:
  python scripts/compare_engine_transcripts.py vendor/yapcore/rep_engine_transcript_*.json
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any


def _zone_codes(zone: Any) -> tuple[int, ...]:
    vals: list[int] = []
    if isinstance(zone, list):
        for c in zone:
            if isinstance(c, dict) and "code" in c:
                vals.append(int(c["code"]))
    return tuple(sorted(vals))


def _state_sig(state: dict) -> tuple:
    primary = state.get("primary", {}) if isinstance(state, dict) else {}
    return (
        _zone_codes(primary.get("hand", [])),
        _zone_codes(primary.get("mzone", [])),
        _zone_codes(primary.get("szone", [])),
        _zone_codes(primary.get("grave", [])),
        _zone_codes(primary.get("banish", [])),
        state.get("to_play"),
        state.get("turn_count"),
        state.get("phase"),
    )


def _node_sig(node: dict) -> tuple:
    chosen = node.get("chosen", {}) if isinstance(node, dict) else {}
    return (
        node.get("prompt_key"),
        chosen.get("action_index"),
        chosen.get("msg_id"),
        chosen.get("act_id"),
        chosen.get("phase_id"),
        chosen.get("label"),
        _state_sig(node.get("before", {})),
        _state_sig(node.get("after", {})),
    )


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare engine transcript JSON files")
    ap.add_argument("inputs", nargs="+", help="Files or globs")
    args = ap.parse_args()

    paths: list[Path] = []
    for raw in args.inputs:
        matched = sorted(glob.glob(raw))
        if matched:
            paths.extend(Path(p) for p in matched)
        else:
            p = Path(raw)
            if p.exists():
                paths.append(p)

    uniq: list[Path] = []
    seen = set()
    for p in paths:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    paths = uniq

    if len(paths) < 2:
        print("Need at least 2 transcript files.")
        return 2

    payloads = [(p, _load(p)) for p in paths]
    base_path, base = payloads[0]
    base_nodes = base.get("nodes", [])
    print(f"Baseline: {base_path} (steps={len(base_nodes)})")

    all_ok = True
    for p, cur in payloads[1:]:
        nodes = cur.get("nodes", [])
        n = min(len(base_nodes), len(nodes))
        mismatch = None
        for i in range(n):
            if _node_sig(base_nodes[i]) != _node_sig(nodes[i]):
                mismatch = i + 1
                break
        if mismatch is not None:
            all_ok = False
            print(f"[DIFF] {p} first mismatch at step {mismatch}")
            b = base_nodes[mismatch - 1]
            c = nodes[mismatch - 1]
            print(
                f"  baseline: {b.get('chosen', {}).get('label')} | "
                f"prompt={b.get('prompt_key')}"
            )
            print(
                f"  current : {c.get('chosen', {}).get('label')} | "
                f"prompt={c.get('prompt_key')}"
            )
        elif len(base_nodes) != len(nodes):
            all_ok = False
            print(f"[DIFF] {p} same prefix, different length: base={len(base_nodes)} current={len(nodes)}")
        else:
            print(f"[OK]   {p} matches baseline exactly ({len(nodes)} steps)")

    if all_ok:
        print("All transcripts are consistent.")
        return 0
    print("Transcript differences found.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
