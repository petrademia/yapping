from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class RobustChoice:
    choice: str
    score: float
    worst_case: str


def robust_choice(payoffs: Mapping[str, Mapping[str, float]]) -> RobustChoice:
    """Choose one pre-reveal action with the strongest worst hidden outcome."""
    if not payoffs or any(not outcomes for outcomes in payoffs.values()):
        raise ValueError("each choice needs at least one hidden outcome")
    candidates = []
    for choice, outcomes in payoffs.items():
        scenario, score = min(outcomes.items(), key=lambda item: item[1])
        candidates.append(RobustChoice(choice, float(score), scenario))
    return max(candidates, key=lambda result: result.score)


def expected_choice(
    payoffs: Mapping[str, Mapping[str, float]],
    probabilities: Mapping[str, float],
) -> tuple[str, float]:
    """Choose one pre-reveal action with the highest weighted outcome."""
    if not probabilities or any(value < 0 for value in probabilities.values()):
        raise ValueError("probabilities must be non-negative")
    if abs(sum(probabilities.values()) - 1) > 1e-9:
        raise ValueError("probabilities must sum to 1")
    if not payoffs or any(not probabilities.keys() <= outcomes.keys()
                          for outcomes in payoffs.values()):
        raise ValueError("each choice needs every probabilistic outcome")
    values = {
        choice: sum(probabilities[scenario] * outcomes[scenario]
                    for scenario in probabilities)
        for choice, outcomes in payoffs.items()
    }
    return max(values.items(), key=lambda item: item[1])
