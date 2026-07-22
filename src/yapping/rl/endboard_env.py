"""Small, masked OCGCore environment for endboard-reaching experiments."""

from pathlib import Path

import gymnasium as gym
import numpy as np

from .._ocgcore import Duel


HAND, MZONE, SZONE, GRAVE, REMOVED = 2, 4, 8, 16, 32
DEFAULT_FILLER = 89631139  # Celtic Guardian
ZONES = (HAND, MZONE, SZONE, GRAVE, REMOVED)


class BrandedEndboardReachEnv(gym.Env):
    """One-turn, no-interruption, fixed-hand OCGCore learning task.

    The environment never chooses a combo action for the agent. OCGCore is
    authoritative for transitions and legal actions; the target endboard is
    only used by the reward evaluator.
    """

    metadata = {"render_modes": []}

    def __init__(self, config, database="assets/cards.cdb", scripts=None,
                 opening_hand=None, max_steps=80, max_actions=128):
        self.config = config
        self.database = Path(database)
        self.scripts = Path(scripts or self.database.parent.parent / "fluorohydride-ygopro-scripts")
        self.opening_hand = tuple(opening_hand or config.get("opening_hand", ()))
        if len(self.opening_hand) != 5:
            raise ValueError("opening_hand must contain exactly five card IDs")
        self.max_steps = int(max_steps)
        self.max_actions = int(max_actions)
        self.card_ids = tuple(sorted(set(config["main_deck"] + config.get("extra_deck", [])
                                         + config.get("target_endboard", []))))
        if not self.card_ids:
            raise ValueError("config must contain cards")
        self._card_index = {card: index for index, card in enumerate(self.card_ids)}
        self.action_space = gym.spaces.Discrete(self.max_actions)
        self.observation_space = gym.spaces.Dict({
            "state": gym.spaces.Box(low=0, high=np.inf,
                                     shape=(3 + len(ZONES) * len(self.card_ids),),
                                     dtype=np.float32),
            "action_mask": gym.spaces.MultiBinary(self.max_actions),
        })
        self._adapter = Duel(str(self.database), str(self.scripts))
        self._decision = None
        self._steps = 0
        self._previous_score = 0.0

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        deck = list(self.config["main_deck"])
        remaining = list(deck)
        for card in self.opening_hand:
            remaining.remove(card)
        deck = [*self.opening_hand, *remaining]
        opponent = [int(self.config.get("opponent_filler", DEFAULT_FILLER))] * 40
        self._decision = self._adapter.reset(
            deck, opponent, list(self.config.get("extra_deck", ())), seed=int(seed or 11)
        )
        self._steps = 0
        self._previous_score = self._score()
        return self._observation(), self._info()

    def step(self, action):
        if self._decision is None:
            raise RuntimeError("reset() must be called before step()")
        action = int(action)
        legal = self._legal_actions()
        if action not in legal:
            raise ValueError(f"illegal action {action}; legal actions are {legal}")
        self._decision = self._adapter.step(action)
        self._steps += 1
        score = self._score()
        shaped = score - self._previous_score
        self._previous_score = score
        terminated = self._is_terminal()
        truncated = self._steps >= self.max_steps and not terminated
        reward = shaped + (score if terminated else 0.0)
        return self._observation(), float(reward), terminated, truncated, self._info(score)

    def _legal_actions(self):
        if self._decision is None:
            return ()
        actions = self._decision["actions"]
        # The benchmark is about combo construction, not battle resolution.
        return tuple(index for index, action in enumerate(actions)
                     if action["kind"] not in {"battle_phase", "shuffle"})

    def _cards(self, location):
        return self._adapter.cards(0, location)

    def _score(self):
        target = set(self.config.get("target_endboard", ()))
        board = set(self._cards(MZONE) + self._cards(SZONE))
        return float(len(target.intersection(board)))

    def _is_terminal(self):
        return bool(self._decision and (
            self._decision["turn"] > self.config.get("terminal_turn", 1)
            or set(self.config.get("target_endboard", ())).issubset(
                set(self._cards(MZONE) + self._cards(SZONE))
            )))

    def _observation(self):
        state = [float(self._decision["turn"]), float(self._decision["phase"]),
                 float(self._decision["player"])]
        for location in ZONES:
            counts = [0.0] * len(self.card_ids)
            for card in self._cards(location):
                if card in self._card_index:
                    counts[self._card_index[card]] += 1.0
            state.extend(counts)
        mask = np.zeros(self.max_actions, dtype=np.int8)
        legal = self._legal_actions()
        if len(legal) > self.max_actions:
            raise RuntimeError("max_actions is smaller than an OCGCore decision")
        mask[list(legal)] = 1
        return {"state": np.asarray(state, dtype=np.float32), "action_mask": mask}

    def _info(self, score=None):
        score = self._score() if score is None else score
        return {"endboard_score": score, "steps": self._steps,
                "target_endboard": tuple(self.config.get("target_endboard", ())),
                "decision": self._decision}
