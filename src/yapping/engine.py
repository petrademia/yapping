from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class Decision:
    observation: NDArray[np.float32]
    legal_actions: tuple[int, ...]
    reward: float = 0.0
    terminated: bool = False
    winner: int | None = None


class Engine(Protocol):
    observation_size: int
    max_actions: int

    def reset(self, seed: int | None = None) -> Decision: ...

    def step(self, action: int) -> Decision: ...

    def state_key(self) -> bytes: ...
