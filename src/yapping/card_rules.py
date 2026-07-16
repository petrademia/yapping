"""Card-database-backed declarative legality rules for combo fixtures."""
from dataclasses import dataclass
import sqlite3
from pathlib import Path

TYPE_FUSION = 0x40


@dataclass(frozen=True)
class CardRecord:
    id: int
    name: str
    type: int
    attribute: int
    race: int
    level: int
    attack: int
    defense: int


class CardDatabase:
    def __init__(self, path: str | Path):
        self._connection = sqlite3.connect(str(path))
        self._connection.row_factory = sqlite3.Row
        self._cache: dict[int, CardRecord] = {}

    def card(self, card_id: int) -> CardRecord:
        if card_id not in self._cache:
            row = self._connection.execute(
                "SELECT d.id, t.name, d.type, d.attribute, d.race, d.level, "
                "d.atk, d.def FROM datas d JOIN texts t ON d.id = t.id "
                "WHERE d.id = ?", (card_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown card id: {card_id}")
            self._cache[card_id] = CardRecord(*row)
        return self._cache[card_id]

    def matching_targets(
        self,
        revealed_card: int,
        extra_deck: list[int],
        predicate: dict[str, int | str],
    ) -> list[CardRecord]:
        """Return Extra Deck cards matching a declarative target predicate."""
        revealed = self.card(revealed_card)
        return [
            candidate for card_id in extra_deck
            for candidate in [self.card(card_id)]
            if (predicate.get("extra_deck_type") != "fusion" or candidate.type & TYPE_FUSION)
            and (not predicate.get("level") or candidate.level == int(predicate["level"]))
            and (
                predicate.get("same_race_as") != "revealed_hand_card"
                or candidate.race == revealed.race
            )
            and (
                not predicate.get("attack_or_defense")
                or candidate.attack == int(predicate["attack_or_defense"])
                or candidate.defense == int(predicate["attack_or_defense"])
            )
        ]

    def high_spirits_targets(self, revealed_card: int, extra_deck: list[int]) -> list[CardRecord]:
        """Backward-compatible Branded fixture helper."""
        return self.matching_targets(revealed_card, extra_deck, {
            "extra_deck_type": "fusion",
            "level": 8,
            "same_race_as": "revealed_hand_card",
            "attack_or_defense": 2500,
        })
