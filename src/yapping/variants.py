"""Immutable deck variants for slot and matchup experiments."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SlotCandidate:
    card_id: int
    role: str
    label: str = ""


@dataclass(frozen=True)
class DeckVariant:
    name: str
    main_deck: tuple[int, ...]
    extra_deck: tuple[int, ...] = ()

    @classmethod
    def from_config(cls, config: dict, name: str | None = None):
        return cls(
            name or str(config["name"]),
            tuple(int(card) for card in config["main_deck"]),
            tuple(int(card) for card in config.get("extra_deck", ())),
        )

    def replace_one(self, remove_card: int, add_card: int, name: str | None = None):
        deck = list(self.main_deck)
        try:
            deck[deck.index(remove_card)] = int(add_card)
        except ValueError as error:
            raise ValueError(f"card {remove_card} is not in {self.name}") from error
        return DeckVariant(name or f"{self.name}+{add_card}-{remove_card}",
                           tuple(deck), self.extra_deck)

    def variants(self, candidates: Iterable[SlotCandidate], remove_card: int):
        return tuple(self.replace_one(remove_card, candidate.card_id,
                                      f"{self.name}+{candidate.label or candidate.card_id}")
                     for candidate in candidates)
