"""Required-piece endboard matching and report payloads for target-board search."""

import time

from collections.abc import Callable, Mapping, Sequence
from typing import Any

ZONES = ("monster", "spell_trap", "grave", "hand", "banished")


def parse_target(value: str, resolve_card: Callable[[str], int]) -> tuple[str, int]:
    if "=" not in value:
        raise ValueError("target must be ZONE=CARD")
    zone, _, card = value.partition("=")
    if zone not in ZONES:
        raise ValueError(f"unknown zone {zone!r}; expected one of {', '.join(ZONES)}")
    if not card:
        raise ValueError("target must be ZONE=CARD")
    return zone, int(resolve_card(card))


def parse_targets(
    values: Sequence[str], resolve_card: Callable[[str], int]
) -> tuple[tuple[str, int], ...]:
    return tuple(parse_target(value, resolve_card) for value in values)


def coverage(
    zones: Mapping[str, Sequence[int]],
    targets: Sequence[tuple[str, int]],
) -> dict[str, Any]:
    remaining: dict[str, list[int]] = {zone: list(zones.get(zone, ())) for zone in ZONES}
    present = []
    missing = []
    for zone, card in targets:
        pile = remaining.setdefault(zone, [])
        try:
            pile.remove(card)
        except ValueError:
            missing.append({"zone": zone, "card": card})
        else:
            present.append({"zone": zone, "card": card})
    return {
        "coverage": len(present),
        "required": len(targets),
        "present": present,
        "missing": missing,
        "complete_match": not missing,
    }


def validate_targets_in_deck(
    main_deck: Sequence[int],
    extra_deck: Sequence[int],
    targets: Sequence[tuple[str, int]],
) -> None:
    pool = set(main_deck) | set(extra_deck)
    for _zone, card in targets:
        if card not in pool:
            raise ValueError(f"required card {card} is not in this deck")


def build_report(
    *,
    event: str,
    coverage_info: Mapping[str, Any],
    targets: Sequence[tuple[str, int]],
    opening_hand: Sequence[int],
    actions: Sequence[str],
    endboard: Mapping[str, Sequence[int]],
    visited_states: int,
    elapsed_seconds: float,
    complete: bool,
    max_nodes: int,
    max_depth: int,
) -> dict[str, Any]:
    return {
        "event": event,
        "complete_match": bool(coverage_info["complete_match"]),
        "coverage": int(coverage_info["coverage"]),
        "required": int(coverage_info["required"]),
        "present": list(coverage_info["present"]),
        "missing": list(coverage_info["missing"]),
        "targets": [{"zone": zone, "card": card} for zone, card in targets],
        "opening_hand": list(opening_hand),
        "actions": list(actions),
        "endboard": {name: list(cards) for name, cards in endboard.items()},
        "visited_states": int(visited_states),
        "elapsed_seconds": float(elapsed_seconds),
        "complete": bool(complete),
        "max_nodes": int(max_nodes),
        "max_depth": int(max_depth),
    }


class ProgressClock:
    """Track the best leaf and emit it every interval_seconds (0 disables dumps)."""

    def __init__(
        self,
        interval_seconds: float,
        write: Callable[[dict], None],
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.interval = float(interval_seconds)
        self.write = write
        self.monotonic = monotonic
        self.started = monotonic()
        self.next_dump = (
            self.started + self.interval if self.interval > 0 else float("inf")
        )
        self.best: tuple[float, dict] | None = None

    def note_leaf(self, score: float, payload: dict) -> None:
        if self.best is None or score > self.best[0]:
            self.best = (float(score), dict(payload))
        now = self.monotonic()
        if self.interval > 0 and now >= self.next_dump and self.best is not None:
            elapsed = now - self.started
            dump = dict(self.best[1])
            dump["event"] = "progress"
            dump["elapsed_seconds"] = elapsed
            self.write(dump)
            while self.next_dump <= now:
                self.next_dump += self.interval
