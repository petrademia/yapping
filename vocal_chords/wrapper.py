"""
High-level ygo-env / OCGCore interface.

Wraps the Gymnasium env from izzak98/ygo-env (or sbl1996/ygo-agent) so YAPPING sees:
- reset() -> state, hand, legal_actions
- get_legal_actions() -> list of action indices
- step(action) -> next_state, done, info
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np


class YgoEnvWrapper:
    """
    Thin wrapper around ygoenv so we can:
    - reset(deck_path) and get hand + legal actions
    - step(action_index) and get next state
    """

    def __init__(
        self,
        deck_path: Path,
        ygo_env_root: Path,
        seed: Optional[int] = None,
    ) -> None:
        self._deck_path = Path(deck_path)
        self._ygo_env_root = Path(ygo_env_root)
        self._seed = seed
        self._env: Any = None
        self._obs: Any = None
        self._info: Any = None
        self._create_env()

    def _create_env(self) -> None:
        import ygoenv  # type: ignore
        from ygoenv.ygopro import init_module  # type: ignore

        # izzak98/ygo-env: must call init_module then make(task_id, env_type, deck1=, deck2=, ...)
        root = self._ygo_env_root
        db_path = root / "assets" / "locale" / "en" / "cards.cdb"
        code_list_file = root / "example" / "code_list.txt"
        if not db_path.is_file():
            raise FileNotFoundError(f"cards.cdb not found: {db_path}. Run 'make' in ygo-env to fetch assets.")
        if not code_list_file.is_file():
            raise FileNotFoundError(f"code_list.txt not found: {code_list_file}")

        deck_stem = self._deck_path.stem
        decks = {deck_stem: str(self._deck_path.resolve())}
        init_module(str(db_path), str(code_list_file), decks)

        kwargs = {
            "num_envs": 1,
            "num_threads": 1,
            "deck1": deck_stem,
            "deck2": deck_stem,
            "player": -1,
            "max_options": 24,
            "n_history_actions": 32,
            "play_mode": "self",
            "async_reset": False,
            "verbose": False,
            "record": False,
        }
        if self._seed is not None:
            kwargs["seed"] = int(self._seed)

        self._env = ygoenv.make(
            task_id="YGOPro-v1",
            env_type="gymnasium",
            **kwargs,
        )
        self._num_envs = 1

    def reset(self) -> Tuple[Any, List[int], List[int]]:
        """
        Reset with the deck; draw opening hand. Returns (obs, hand_indices, legal_action_indices).
        hand_indices / legal_action_indices may be raw engine indices if card names not available.
        """
        try:
            out = self._env.reset(seed=self._seed)
        except TypeError:
            out = self._env.reset()

        if isinstance(out, (list, tuple)) and len(out) >= 2:
            self._obs, self._info = out[0], out[1]
        else:
            self._obs, self._info = out, {}

        # EnvPool returns batched obs (num_envs, ...); we use env 0
        obs_0 = self._index_batch(self._obs, 0)
        hand = self._get_hand_from_obs(obs_0)
        legal = self._get_legal_actions_from_obs(obs_0)
        return self._obs, hand, legal

    def _index_batch(self, obs: Any, idx: int) -> Any:
        """Index batched obs to get single-env obs (for num_envs=1)."""
        if obs is None:
            return None
        if hasattr(obs, "get"):
            return {k: (v[idx] if hasattr(v, "__getitem__") and not isinstance(v, (str, bytes)) else v)
                    for k, v in obs.items()}
        return obs[idx] if hasattr(obs, "__getitem__") else obs

    def _get_hand_from_obs(self, obs: Any) -> List[int]:
        """Extract hand (card indices or IDs) from observation."""
        if obs is None:
            return []
        if hasattr(obs, "get"):
            # Dict-like (Gymnasium Dict space)
            cards = obs.get("cards_") or obs.get("cards") or obs.get("hand")
            if cards is not None:
                arr = np.asarray(cards)
                if arr.ndim >= 2:
                    # First row or first 5 might be hand; engine-specific
                    return arr.flatten()[:5].tolist()
                return arr.flatten().tolist()[:5]
            global_ = obs.get("global_")
            if global_ is not None:
                return []
        return []

    def _get_legal_actions_from_obs(self, obs: Any) -> List[int]:
        """Extract legal action indices from observation (mask or list)."""
        if obs is None:
            return []
        if hasattr(obs, "get"):
            mask = obs.get("mask_") or obs.get("action_mask") or obs.get("mask")
            if mask is not None:
                m = np.asarray(mask)
                indices = np.where(m.flatten() != 0)[0]
                return indices.tolist()
            acts = obs.get("legal_actions") or obs.get("actions_")
            if acts is not None:
                a = np.asarray(acts)
                return a.flatten().tolist()
        return []

    def get_legal_actions(self) -> List[int]:
        """Current step's legal action indices (from last obs)."""
        obs_0 = self._index_batch(self._obs, 0)
        return self._get_legal_actions_from_obs(obs_0)

    def get_hand(self) -> List[int]:
        """Current hand (raw indices/IDs from last obs)."""
        obs_0 = self._index_batch(self._obs, 0)
        return self._get_hand_from_obs(obs_0)

    def step(self, action: int) -> Tuple[Any, bool, bool, Any]:
        """Step with action index. Returns (obs, terminated, truncated, info)."""
        # EnvPool expects batched action (num_envs,)
        action_batch = np.array([action], dtype=np.int64)
        out = self._env.step(action_batch)
        # Gymnasium: step returns (obs, reward, terminated, truncated, info)
        if isinstance(out, (list, tuple)):
            if len(out) >= 5:
                self._obs, _reward, term, trunc, self._info = out[0], out[1], out[2], out[3], out[4]
                t, tr = (term[0] if hasattr(term, "__getitem__") else term), (trunc[0] if hasattr(trunc, "__getitem__") else trunc)
                return self._obs, bool(t), bool(tr), self._info
            if len(out) >= 4:
                self._obs, _reward, done, self._info = out[0], out[1], out[2], out[3]
                d = done[0] if hasattr(done, "__getitem__") else done
                return self._obs, bool(d), False, self._info
        self._obs = out
        return self._obs, False, False, {}

    @property
    def raw_env(self) -> Any:
        """Access underlying env for engine-specific options."""
        return self._env
