"""Archetype-independent, location-aware endboard evaluation."""
from dataclasses import dataclass, field
from typing import Iterable, Mapping


@dataclass(frozen=True)
class EvaluationState:
    zones: Mapping[str, tuple[int, ...]]
    facts: Mapping[str, object] = field(default_factory=dict)


class EndboardEvaluator:
    """Score a board using card weights and state facts supplied by the caller."""

    def __init__(
        self,
        card_weights: Mapping[int, float],
        objectives: Mapping[str, float] | None = None,
        unknown_card_weight: float = 0.5,
    ):
        self.card_weights = dict(card_weights)
        self.objectives = dict(objectives or {})
        self.unknown_card_weight = unknown_card_weight

    def card_value(self, card_id: int) -> float:
        return float(self.card_weights.get(card_id, self.unknown_card_weight))

    def breakdown(self, state: EvaluationState) -> dict[str, float]:
        zones = state.zones
        return {
            "generic_hand": len(zones.get("hand", ())) * self.objectives.get("card_advantage", 0.25),
            "monsters": sum(self.card_value(card) for card in zones.get("monster", ())),
            "spell_traps": sum(self.card_value(card) for card in zones.get("spell_trap", ())),
            "named_hand_followup": sum(self.card_weights.get(card, 0.0) for card in zones.get("hand", ())),
            "grave_resources": sum(self.card_value(card) for card in zones.get("grave", ()))
                * self.objectives.get("grave_resource", 0.0),
            "survival": float(state.facts.get("opponent_interrupted", False))
                * self.objectives.get("disruption_survived", 0.0),
        }

    def score(self, state: EvaluationState) -> float:
        return sum(self.breakdown(state).values())


def zones_from_iterables(zones: Mapping[str, Iterable[int]]) -> dict[str, tuple[int, ...]]:
    return {name: tuple(cards) for name, cards in zones.items()}
