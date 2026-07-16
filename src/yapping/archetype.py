"""Declarative archetype data used by search and evaluation tools."""

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Fixture:
    id: str
    path: Path


@dataclass(frozen=True)
class Interruption:
    name: str
    card_id: int
    policy: str


@dataclass(frozen=True)
class Archetype:
    name: str
    main_deck: tuple[int, ...]
    extra_deck: tuple[int, ...]
    interruptions: dict[str, Interruption]
    fixtures: tuple[Fixture, ...]
    target_predicates: dict[str, dict[str, Any]]
    card_weights: dict[int, float]
    objectives: dict[str, float]
    metadata: dict[str, Any]

    @property
    def deck_counts(self) -> Counter[int]:
        return Counter(self.main_deck)

    @property
    def extra_deck_counts(self) -> Counter[int]:
        return Counter(self.extra_deck)


def load_archetype(path: str | Path) -> Archetype:
    """Load an archetype and resolve fixture paths beside its JSON file."""
    source = Path(path).resolve()
    with source.open(encoding="utf-8") as handle:
        data = json.load(handle)
    interruptions = {
        name: Interruption(name, int(spec["card_id"]), str(spec["policy"]))
        for name, spec in data.get("interruption_specs", {}).items()
    }
    fixtures = tuple(
        Fixture(str(item["id"]), (source.parent / item["path"]).resolve())
        for item in data.get("fixtures", [])
    )
    return Archetype(
        name=str(data["name"]),
        main_deck=tuple(int(card) for card in data.get("main_deck", [])),
        extra_deck=tuple(int(card) for card in data.get("extra_deck", [])),
        interruptions=interruptions,
        fixtures=fixtures,
        target_predicates=dict(data.get("target_predicates", {})),
        card_weights={int(card): float(value) for card, value in data.get("card_weights", {}).items()},
        objectives={name: float(value) for name, value in data.get("objectives", {}).items()},
        metadata=dict(data.get("metadata", {})),
    )
