"""Card-database-backed legality rules for combo fixtures."""
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

    def high_spirits_targets(self, revealed_card: int, extra_deck: list[int]) -> list[CardRecord]:
        """Return legal Level 8 Fusion targets for Branded in High Spirits."""
        revealed = self.card(revealed_card)
        return [
            candidate for card_id in extra_deck
            for candidate in [self.card(card_id)]
            if candidate.type & TYPE_FUSION
            and candidate.level == 8
            and candidate.race == revealed.race
            and (candidate.attack == 2500 or candidate.defense == 2500)
        ]
