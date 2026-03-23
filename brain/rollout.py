"""
Rollout engine for MDP data and RL.

Generate trajectories: reset → Main Phase → (state, action, reward) loop until
depth limit or game end. Log each step so you can sanity-check the MDP.

MDP:
  - State: summary of (hand, board_score, num_legal). Raw obs via env.get_obs().
  - Action: index in get_legal_actions() (same as DFS).
  - Reward: evaluate_board(obs) after each step (or at end only).
  - Episode: one hand, play until max_depth or no legal actions or terminated.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal

from engine.actions import decode_action_features
from engine.idle import complete_until_main_phase_idle, wait_until_main_phase_idle

from brain.heuristics import evaluate_board


@dataclass
class StateSummary:
    """Compact state for logging (hand codes, board score, num legal actions)."""
    hand: List[int]
    board_score: int
    num_legal: int
    step: int

    def to_dict(self) -> dict:
        return {
            "hand": self.hand,
            "board_score": self.board_score,
            "num_legal": self.num_legal,
            "step": self.step,
        }


@dataclass
class StepRecord:
    """One (state, action, reward) transition."""
    state: StateSummary
    action_index: int
    action_label: str
    reward_after: int
    terminated: bool

    def to_dict(self, cid_map: dict, name_map: dict) -> dict:
        hand_codes = [cid_map.get(h, h) for h in self.state.hand]
        return {
            "state": self.state.to_dict(),
            "hand_codes": hand_codes,
            "action_index": self.action_index,
            "action_label": self.action_label,
            "reward_after": self.reward_after,
            "terminated": self.terminated,
        }


@dataclass
class Trajectory:
    """One episode: list of step records and final return."""
    steps: List[StepRecord] = field(default_factory=list)
    final_return: int = 0
    seed: int | None = None

    def to_dict(self, cid_map: dict, name_map: dict) -> dict:
        return {
            "seed": self.seed,
            "final_return": self.final_return,
            "num_steps": len(self.steps),
            "steps": [s.to_dict(cid_map, name_map) for s in self.steps],
        }


def _state_summary(env, step: int) -> StateSummary:
    obs = env.get_obs()
    hand = env.get_hand()
    legal = env.get_legal_actions()
    score = evaluate_board(obs)
    return StateSummary(hand=list(hand), board_score=score, num_legal=len(legal), step=step)


def run_episode(
    env,
    cid_map: dict,
    name_map: dict,
    *,
    max_depth: int = 10,
    policy: Literal["random", "greedy_pass_last"] = "random",
    reward_shape: Literal["step", "final_only"] = "step",
    seed: int | None = None,
) -> Trajectory:
    """
    Run one episode: reset, wait Main Phase, then loop (state → choose action → step → complete → record).

    policy:
      - "random": uniform over legal actions.
      - "greedy_pass_last": same as random but put Pass last (so we try non-Pass first when random).
    reward_shape:
      - "step": reward = evaluate_board(obs) after each step (so you see progression).
      - "final_only": reward = 0 except at end; final_return is still set.
    """
    if seed is not None:
        random.seed(seed)
    traj = Trajectory(seed=seed)

    obs, _, _ = env.reset(seed=seed)
    if not wait_until_main_phase_idle(env, cid_map, name_map):
        return traj

    step = 0
    while step < max_depth:
        state = _state_summary(env, step)
        actions = env.get_legal_actions()
        if not actions:
            traj.final_return = state.board_score
            break

        # Policy: choose action index
        if policy == "random":
            action_index = random.choice(actions)
        elif policy == "greedy_pass_last":
            # Prefer non-Pass: put Pass at end, then random among the rest
            labels = [
                decode_action_features(env.action_features(i), cid_map, name_map) or ""
                for i in actions
            ]
            non_pass = [actions[i] for i in range(len(actions)) if "Pass" not in labels[i]]
            pass_actions = [actions[i] for i in range(len(actions)) if "Pass" in labels[i]]
            ordered = non_pass + pass_actions
            action_index = random.choice(ordered) if ordered else actions[0]
        else:
            action_index = random.choice(actions)

        feat = env.action_features(action_index)
        action_label = decode_action_features(feat, cid_map, name_map) if feat else f"action_{action_index}"

        obs, terminated, truncated, _ = env.step(action_index)
        if not terminated and not truncated:
            complete_until_main_phase_idle(env, cid_map, name_map)
            obs = env.get_obs()

        reward = evaluate_board(obs) if obs else 0
        traj.final_return = reward

        if reward_shape == "step":
            r = reward
        else:
            r = 0

        traj.steps.append(
            StepRecord(
                state=state,
                action_index=action_index,
                action_label=action_label,
                reward_after=r,
                terminated=terminated or truncated,
            )
        )

        if terminated or truncated:
            break
        step += 1

    return traj


def run_rollouts(
    env,
    cid_map: dict,
    name_map: dict,
    num_episodes: int = 5,
    max_depth: int = 10,
    policy: Literal["random", "greedy_pass_last"] = "random",
    reward_shape: Literal["step", "final_only"] = "step",
    log_path: Path | None = None,
    verbose: bool = True,
) -> List[Trajectory]:
    """Run multiple episodes and optionally log to JSON."""
    trajectories = []
    for ep in range(num_episodes):
        seed = random.randint(1, 2**31 - 1)
        traj = run_episode(
            env, cid_map, name_map,
            max_depth=max_depth,
            policy=policy,
            reward_shape=reward_shape,
            seed=seed,
        )
        trajectories.append(traj)
        if verbose:
            steps = len(traj.steps)
            ret = traj.final_return
            path_str = " → ".join(s.action_label for s in traj.steps[:5])
            if len(traj.steps) > 5:
                path_str += " ..."
            print(f"  episode {ep+1}/{num_episodes}  steps={steps}  return={ret}  {path_str}")

    if log_path is not None:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "num_episodes": num_episodes,
            "max_depth": max_depth,
            "policy": policy,
            "reward_shape": reward_shape,
            "trajectories": [t.to_dict(cid_map, name_map) for t in trajectories],
        }
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if verbose:
            print(f"  Logged to {log_path}")

    return trajectories
