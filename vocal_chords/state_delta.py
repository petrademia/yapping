"""
Helpers for deriving zone deltas and coarse action tags from named state snapshots.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

_ZONE_KEYS = ("hand", "mzone", "szone", "grave", "banish")


def _zones_view(state: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not state:
        return {k: [] for k in _ZONE_KEYS}
    src = state.get("primary") if isinstance(state.get("primary"), dict) else state
    out: dict[str, list[dict[str, Any]]] = {}
    for key in _ZONE_KEYS:
        vals = src.get(key, []) if isinstance(src, dict) else []
        out[key] = [v for v in vals if isinstance(v, dict)]
    return out


def _card_key(card: dict[str, Any]) -> tuple[str, int]:
    name = str(card.get("name") or card.get("code") or card.get("card_id") or "?")
    cid = int(card.get("card_id") or 0)
    return name, cid


def _counter(cards: list[dict[str, Any]]) -> Counter:
    c: Counter = Counter()
    for card in cards:
        c[_card_key(card)] += 1
    return c


def _expand(counter: Counter) -> list[str]:
    out: list[str] = []
    for (name, _cid), n in sorted(counter.items(), key=lambda x: (x[0][0], x[0][1])):
        for _ in range(int(n)):
            out.append(name)
    return out


def summarize_state_delta(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:
    bz = _zones_view(before)
    az = _zones_view(after)
    moved: list[dict[str, Any]] = []
    per_zone: dict[str, dict[str, list[str]]] = {}

    for key in _ZONE_KEYS:
        b = _counter(bz[key])
        a = _counter(az[key])
        left = b - a
        entered = a - b
        per_zone[key] = {"left": _expand(left), "entered": _expand(entered)}

    # Best-effort movement reconstruction by matching exact (name, card_id) across zones.
    for src in _ZONE_KEYS:
        left = _counter(bz[src]) - _counter(az[src])
        for dst in _ZONE_KEYS:
            if src == dst:
                continue
            entered = _counter(az[dst]) - _counter(bz[dst])
            common = left & entered
            for (name, _cid), n in common.items():
                for _ in range(int(n)):
                    moved.append({"card": name, "from": src, "to": dst})
            left -= common

    moved_unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in moved:
        key = (str(row["card"]), str(row["from"]), str(row["to"]))
        if key in seen:
            continue
        seen.add(key)
        moved_unique.append(row)

    tags: list[str] = []
    if any(m["to"] == "mzone" for m in moved):
        tags.append("develops_monster")
    if any(m["to"] == "szone" for m in moved):
        tags.append("develops_spell_trap")
    if any(m["to"] == "grave" for m in moved):
        tags.append("sends_to_grave")
    if any(m["to"] == "banish" for m in moved):
        tags.append("banishes")
    if any(m["to"] == "hand" for m in moved):
        tags.append("adds_to_hand")
    if any(m["from"] == "mzone" and m["to"] == "grave" for m in moved):
        tags.append("trades_board_for_grave")
    if any(m["from"] == "hand" and m["to"] == "mzone" for m in moved):
        tags.append("commits_from_hand")
    if any(m["from"] == "hand" and m["to"] == "grave" for m in moved):
        tags.append("discards_or_sends_from_hand")

    return {
        "per_zone": per_zone,
        "moved": moved_unique,
        "derived_tags": tags,
    }

