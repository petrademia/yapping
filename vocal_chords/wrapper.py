"""
High-level ygo-env / OCGCore interface.

Wraps the Gymnasium env from ygo-env (petrademia fork or izzak98/sbl1996) so YAPPING sees:
- reset() -> state, hand, legal_actions
- get_legal_actions() -> list of action indices
- step(action) -> next_state, done, info
"""

from __future__ import annotations

import os
import random
import shutil
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

import numpy as np


class YgoEnvWrapper:
    """
    Thin wrapper around ygoenv so we can:
    - reset(deck_path) and get hand + legal actions
    - step(action_index) and get next state
    """

    _module_initialized = False

    def __init__(
        self,
        deck_path: Path,
        ygo_env_root: Path,
        seed: Optional[int] = None,
        player: int = 0,
        engine_verbose: bool = False,
    ) -> None:
        self._deck_path = Path(deck_path)
        self._ygo_env_root = Path(ygo_env_root)
        # If no seed given, pick a random one so each run shuffles the deck
        # differently. envpool seeds the PRNG at make() time and doesn't
        # re-randomise on reset() when no seed was provided, so without this
        # every invocation would draw the same opening hand.
        self._seed = seed if seed is not None else random.randint(0, 2**31 - 1)
        self._user_seed = seed  # None means "random" — exposed for display
        self._player = int(player)
        self._engine_verbose = bool(engine_verbose)
        self._env: Any = None
        self._obs: Any = None
        self._info: Any = None
        self._create_env()

    def _create_env(self) -> None:
        # Ensure we load the real ygoenv package (editable install); when cwd is ygo-env root,
        # the dir ygo-env/ygoenv can shadow it and break ygoenv.make.
        import sys
        root = self._ygo_env_root
        _ygoenv_pkg = root / "ygoenv"
        if _ygoenv_pkg.is_dir():
            _pkg = str(_ygoenv_pkg.resolve())
            if _pkg not in sys.path:
                sys.path.insert(0, _pkg)

        from ygoenv.ygopro import init_module  # type: ignore
        import ygoenv.ygopro.registration  # noqa: F401  (registers YGOPro-v1)
        from ygoenv.registration import make  # type: ignore

        # ygo-env (petrademia/izzak98): must call init_module then make(task_id, env_type, deck1=, deck2=, ...)
        db_path = root / "assets" / "locale" / "en" / "cards.cdb"
        code_list_file = root / "example" / "code_list.txt"
        if not db_path.is_file():
            raise FileNotFoundError(f"cards.cdb not found: {db_path}. Run 'make assets scripts' in ygo-env to fetch assets.")
        if not code_list_file.is_file():
            raise FileNotFoundError(f"code_list.txt not found: {code_list_file}")

        deck_stem = self._deck_path.stem
        decks = {deck_stem: str(self._deck_path.resolve())}
        # Merge deck card codes into code list so "Card not found" is avoided for deck cards
        code_list_to_use = self._merged_code_list(root, code_list_file, self._deck_path)
        
        if not YgoEnvWrapper._module_initialized:
            # Use absolute paths so the C++ finds files regardless of cwd
            init_module(str(db_path.resolve()), str(code_list_to_use.resolve()), decks)
            YgoEnvWrapper._module_initialized = True

        kwargs = {
            "num_envs": 1,
            "num_threads": 1,
            "deck1": deck_stem,
            "deck2": deck_stem,
            # Keep a fixed POV player to avoid perspective flips in observations.
            "player": self._player,
            "max_options": 24,
            "n_history_actions": 32,
            "play_mode": "self",
            "async_reset": False,
            "verbose": self._engine_verbose,
            "record": False,
            # oppo_info=True switches the engine to _set_obs_g_cards mode, which
            # encodes actual card IDs (code_list indices) into obs:cards_[row, 0:2].
            # Without this, cols 0-1 are always 0 and hand cards show as [0, 0, ...].
            "oppo_info": True,
        }
        if self._seed is not None:
            kwargs["seed"] = int(self._seed)

        self._env = make(
            task_id="YGOPro-v1",
            env_type="gymnasium",
            **kwargs,
        )
        self._num_envs = 1

    @staticmethod
    def _deck_codes(deck_path: Path) -> Set[int]:
        """Parse .ydk file and return set of card codes (main + extra + side)."""
        codes: Set[int] = set()
        with open(deck_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip().strip("\r")
                if not line or line.startswith("#"):
                    continue
                if line.isdigit():
                    codes.add(int(line))
        return codes

    @staticmethod
    def _merged_code_list(ygo_root: Path, code_list_file: Path, deck_path: Path) -> Path:
        """
        Build a code list that includes the engine's code_list plus any card codes
        from the deck that are missing. Avoids "[c_get_card] Card not found" for
        deck cards that exist in cards.cdb and have scripts but aren't in the
        bundled example code_list.txt.
        """
        deck_codes = YgoEnvWrapper._deck_codes(deck_path)
        script_dir = ygo_root / "scripts" / "script"
        existing_codes: Set[int] = set()
        original_lines: List[str] = []
        with open(code_list_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                original_lines.append(line)
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    existing_codes.add(int(parts[0]))
        missing = deck_codes - existing_codes
        if not missing:
            return code_list_file
        # Write under ygo-env so the path is on the same filesystem (avoids /tmp path issues in WSL)
        merged_path = ygo_root / "example" / "code_list_merged.txt"
        with open(merged_path, "w", encoding="utf-8") as f:
            f.writelines(original_lines)
            for code in sorted(missing):
                has_script = 1 if (script_dir / f"c{code}.lua").is_file() else 0
                f.write(f"{code} {has_script}\n")
        # Overwrite code_list.txt with merged content so the engine sees it whether it uses
        # the path we pass or a hardcoded relative path. Pass code_list_file to init_module
        # so the engine opens the file we just wrote.
        shutil.copy2(merged_path, code_list_file)
        try:
            os.sync()  # force persistence (helps on WSL when writing to /mnt/c)
        except (AttributeError, OSError):
            pass
        return code_list_file

    def reset(self, seed: Optional[int] = None) -> Tuple[Any, List[int], List[int]]:
        """
        Reset with the deck; draw opening hand. Returns (obs, hand_indices, legal_action_indices).
        hand_indices / legal_action_indices may be raw engine indices if card names not available.
        Optional seed for this reset only (for sampling multiple different hands).
        """
        use_seed = seed if seed is not None else self._seed
        # Keep replay root consistent: if caller forces a seed (e.g. target-card draw),
        # subsequent reset() calls in DFS should return to that exact root state.
        if seed is not None:
            self._seed = int(seed)
        try:
            out = self._env.reset(seed=use_seed)
        except TypeError:
            out = self._env.reset()

        if isinstance(out, (list, tuple)) and len(out) >= 2:
            self._obs, self._info = out[0], out[1]
        else:
            self._obs, self._info = out, {}

        # EnvPool returns batched obs (num_envs, ...); we use env 0
        obs_0 = self._index_batch(self._obs, 0)
        hand = self._get_hand_from_obs(obs_0)
        legal = self._get_legal_actions_from_info_or_obs(obs_0)
        return self._obs, hand, legal

    def _index_batch(self, obs: Any, idx: int) -> Any:
        """Index batched obs to get single-env obs (for num_envs=1)."""
        if obs is None:
            return None
        if hasattr(obs, "get"):
            out = {}
            for k, v in obs.items():
                if isinstance(v, (str, bytes)):
                    out[k] = v
                elif hasattr(v, "__getitem__") and hasattr(v, "shape"):
                    # Only index if first dim looks like batch (e.g. 1); else obs is already single-env
                    try:
                        sh = getattr(v, "shape", ())
                        if len(sh) >= 2 and sh[0] <= 32:  # batch dim, not e.g. 160 cards
                            out[k] = v[idx]
                        else:
                            out[k] = v
                    except (TypeError, IndexError):
                        out[k] = v
                elif hasattr(v, "__getitem__"):
                    out[k] = v[idx] if idx == 0 else v
                else:
                    out[k] = v
            return out
        return obs[idx] if hasattr(obs, "__getitem__") else obs

    def _get_hand_from_obs(self, obs: Any) -> List[int]:
        """Extract hand card_ids from observation.

        With oppo_info=True (required), the engine uses _set_obs_g_cards which encodes:
          col 0-1: card_id (code_list 1-based index, high byte / low byte)
          col 2:   location_to_id(location)  — 2 = LOCATION_HAND
          col 3:   sequence (0 for hand cards)
          col 4:   controller (0 = current player, 1 = opponent)

        Without oppo_info=True, cols 0-1 are always 0 (engine bug/design).
        Cards are written in location order: deck, hand, mzone, szone, grave, removed, extra
        for both players, so hand cards are NOT the first rows in the array."""
        if obs is None:
            return []
        if hasattr(obs, "get"):
            cards = obs.get("obs:cards_")
            if cards is None:
                cards = obs.get("cards_")
            if cards is None:
                cards = obs.get("cards")
            if cards is not None:
                arr = np.asarray(cards, dtype=np.uint8)
                if arr.ndim >= 2 and arr.shape[1] >= 5:
                    # Column 2 = location (2 = LOCATION_HAND per make_ids(..., 1)), column 4 = controller (0 = us)
                    loc_col, ctrl_col = 2, 4
                    in_hand = (arr[:, loc_col] == 2) & (arr[:, ctrl_col] == 0)
                    hand_rows = np.where(in_hand)[0][:5]
                    ids = []
                    for row in hand_rows:
                        cid = int(arr[row, 0]) * 256 + int(arr[row, 1])
                        ids.append(cid)
                    return ids
            cards = obs.get("hand")
            if cards is not None:
                arr = np.asarray(cards)
                return arr.flatten()[:5].tolist()
        return []

    def _get_legal_actions_from_info_or_obs(self, obs: Any) -> List[int]:
        """Return legal action indices 0..N-1.

        Primary source: info['num_options'] set by the engine (most reliable).
        Fallback: count non-zero msg rows in obs['actions_'] (col 3 = msg_to_id).
        The obs['mask_'] field is a per-card attribute mask (shape max_cards*2 x 14),
        NOT a flat action-index mask, so it must not be used here.
        """
        # --- Primary: info['num_options'] ---
        n = self._num_options_from_info()
        if n is not None:
            return list(range(n))

        # --- Fallback: count filled action slots in obs['actions_'] ---
        # actions_ has shape (max_options, n_feats); col 3 = msg_to_id (0 = empty slot).
        if obs is not None and hasattr(obs, "get"):
            acts = obs.get("obs:actions_")
            if acts is None:
                acts = obs.get("actions_")
            if acts is not None:
                a = np.asarray(acts)
                if a.ndim >= 2 and a.shape[1] >= 4:
                    # col 3 = msg; non-zero means the slot holds a real action
                    n_valid = int(np.sum(a[:, 3] != 0))
                    return list(range(n_valid))
                # Older layout: any non-zero row counts as a valid action
                if a.ndim >= 2:
                    n_valid = int(np.sum(np.any(a != 0, axis=1)))
                    return list(range(n_valid))
        return []

    def _num_options_from_info(self) -> Optional[int]:
        """Extract num_options from self._info (set by the engine as info:num_options)."""
        info = self._info
        if info is None:
            return None
        # gymnasium envpool strips the 'info:' prefix; key is 'num_options'
        for key in ("num_options", "info:num_options"):
            val = info.get(key) if hasattr(info, "get") else None
            if val is None and hasattr(info, "__getitem__"):
                try:
                    val = info[key]
                except (KeyError, TypeError):
                    pass
            if val is not None:
                # may be batched (num_envs,); take env 0
                try:
                    v = val[0] if hasattr(val, "__getitem__") else val
                    return int(v)
                except (TypeError, IndexError):
                    pass
        return None

    def _get_legal_actions_from_obs(self, obs: Any) -> List[int]:
        """Deprecated shim kept for compatibility; delegates to new method."""
        return self._get_legal_actions_from_info_or_obs(obs)

    def get_legal_actions(self) -> List[int]:
        """Current step's legal action indices (from last obs/info)."""
        obs_0 = self._index_batch(self._obs, 0)
        return self._get_legal_actions_from_info_or_obs(obs_0)

    def get_hand(self) -> List[int]:
        """Current hand (raw indices/IDs from last obs)."""
        obs_0 = self._index_batch(self._obs, 0)
        return self._get_hand_from_obs(obs_0)

    def get_state_snapshot(self, obs: Any = None) -> dict:
        """
        Extract hand, field (mzone + szone), grave, banish for the current player (controller 0).
        obs: observation from get_obs(); if None, uses current _obs.
        Returns dict with keys: hand, field_mzone, field_szone, grave, banish (each list of card_ids).
        """
        # Location ids (col 2): 2=hand, 3=mzone, 4=szone, 5 or 16=grave, 6=removed
        LOC_HAND, LOC_MZONE, LOC_SZONE, LOC_GRAVE, LOC_GRAVE_ALT, LOC_REMOVED = 2, 3, 4, 5, 16, 6
        empty: List[int] = []
        out = {"hand": empty[:], "field_mzone": empty[:], "field_szone": empty[:], "grave": empty[:], "banish": empty[:]}
        if obs is None:
            obs = self._index_batch(self._obs, 0)
        if obs is None or not hasattr(obs, "get"):
            return out
        cards = obs.get("obs:cards_")
        if cards is None:
            cards = obs.get("cards_")
        if cards is None:
            cards = obs.get("cards")
        if cards is None:
            out["hand"] = self._get_hand_from_obs(obs)
            return out
        arr = np.asarray(cards, dtype=np.uint8)
        if arr.ndim == 3:
            arr = arr[0]
        if arr.ndim < 2 or arr.shape[1] < 5:
            return out
        loc_col, ctrl_col = 2, 4
        ours = arr[:, ctrl_col] == 0
        for row in range(arr.shape[0]):
            if not ours[row]:
                continue
            cid = int(arr[row, 0]) * 256 + int(arr[row, 1])
            loc = int(arr[row, loc_col])
            if loc == LOC_HAND:
                out["hand"].append(cid)
            elif loc == LOC_MZONE:
                out["field_mzone"].append(cid)
            elif loc == LOC_SZONE:
                out["field_szone"].append(cid)
            elif loc in (LOC_GRAVE, LOC_GRAVE_ALT):
                out["grave"].append(cid)
            elif loc == LOC_REMOVED:
                out["banish"].append(cid)
        return out

    def get_obs(self) -> Any:
        """Current observation for env 0 (single-env view). For board evaluation etc."""
        return self._index_batch(self._obs, 0)

    def get_current_phase(self) -> Optional[str]:
        """
        Return current game phase if the engine exposes it in obs or info (e.g. 'draw', 'main1', 'main2', 'battle', 'end').
        Returns None if not available; ygo-env may not expose phase, in which case use action-based heuristics
        (e.g. msg_to_id=1 + Summon/MSet/Set/Activate in legal actions for Main Phase idle).
        """
        for source, key_list in [
            (self._info, ("phase", "game_phase", "info:phase", "info:game_phase", "current_phase")),
            (self._index_batch(self._obs, 0) if self._obs is not None else None, ("phase", "obs:phase", "game_phase")),
        ]:
            if source is None or not hasattr(source, "get"):
                continue
            for key in key_list:
                val = source.get(key)
                if val is not None:
                    try:
                        v = val[0] if hasattr(val, "__getitem__") and not isinstance(val, str) else val
                        return str(v).lower() if v is not None else None
                    except (TypeError, IndexError):
                        pass
        # Fallback: decode phase id from obs:global_[5] (engine phase_to_id).
        obs_0 = self._index_batch(self._obs, 0) if self._obs is not None else None
        if obs_0 is not None and hasattr(obs_0, "get"):
            g = obs_0.get("obs:global_")
            if g is None:
                g = obs_0.get("global_")
            if g is None:
                g = obs_0.get("global")
            if g is not None:
                try:
                    arr = np.asarray(g, dtype=np.uint8)
                    if arr.ndim == 2:
                        arr = arr[0]
                    if arr.ndim >= 1 and arr.shape[0] > 5:
                        pid = int(arr[5])
                        # From ygopro.h phase2str + make_ids order.
                        phase_map = {
                            0: "draw",
                            1: "standby",
                            2: "main1",
                            3: "battle_start",
                            4: "battle_step",
                            5: "damage",
                            6: "damage_cal",
                            7: "battle",
                            8: "main2",
                            9: "end",
                        }
                        return phase_map.get(pid)
                except Exception:
                    pass
        return None

    def get_to_play(self) -> Optional[int]:
        """Return absolute to_play player id (0/1) if exposed by env info, else None."""
        info = self._info
        if info is None or not hasattr(info, "get"):
            return None
        for key in ("to_play", "info:to_play"):
            val = info.get(key)
            if val is None and hasattr(info, "__getitem__"):
                try:
                    val = info[key]
                except (KeyError, TypeError):
                    val = None
            if val is None:
                continue
            try:
                v = val[0] if hasattr(val, "__getitem__") and not isinstance(val, str) else val
                return int(v)
            except (TypeError, ValueError, IndexError):
                continue
        return None

    def get_turn_count(self) -> Optional[int]:
        """Return current turn count from obs:global_[4] when available."""
        obs_0 = self._index_batch(self._obs, 0)
        if obs_0 is None or not hasattr(obs_0, "get"):
            return None
        g = obs_0.get("obs:global_")
        if g is None:
            g = obs_0.get("global_")
        if g is None:
            g = obs_0.get("global")
        if g is None:
            return None
        try:
            arr = np.asarray(g, dtype=np.uint8)
            if arr.ndim == 2:
                arr = arr[0]
            if arr.ndim >= 1 and arr.shape[0] > 4:
                return int(arr[4])
        except Exception:
            return None
        return None

    def action_features(self, action_idx: int) -> List[int]:
        """Return the 12 feature bytes for action_idx from obs['actions_'].

        These can be passed to vocal_chords.actions.decode_action_features()
        to get a human-readable label like 'Summon Aluber the Jester of Despia'.
        Returns an empty list if the index is out of range or obs is unavailable.
        """
        obs_0 = self._index_batch(self._obs, 0)
        if obs_0 is None or not hasattr(obs_0, "get"):
            return []
        acts = obs_0.get("obs:actions_")
        if acts is None:
            acts = obs_0.get("actions_")
        if acts is None:
            return []
        a = np.asarray(acts)
        if a.ndim < 2 or action_idx >= a.shape[0]:
            return []
        return a[action_idx].tolist()

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
