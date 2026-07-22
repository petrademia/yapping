"""Run a small, inspectable masked Q-learning experiment."""

import argparse
import json
import random
from pathlib import Path

from matchup_config import load_config
from yapping.rl import BrandedEndboardReachEnv


ROOT = Path(__file__).parents[1]


def state_key(observation):
    return observation["state"].tobytes()


def train(episodes=100, seed=7, alpha=0.2, gamma=0.98,
          epsilon=1.0, epsilon_min=0.05, epsilon_decay=0.98):
    config = load_config(ROOT / "configs/albaz.json")
    config.update({
        "opening_hand": [73819701, 55273560, 91152256, 91152256, 91152256],
        "target_endboard": [44146295, 17751597, 55273560],
    })
    env = BrandedEndboardReachEnv(
        config, database=ROOT / "assets/cards.cdb",
        scripts=ROOT.parent / "fluorohydride-ygopro-scripts", max_steps=80,
    )
    q = {}
    rng = random.Random(seed)
    history = []
    for episode in range(episodes):
        observation, _ = env.reset(seed=seed + episode)
        total = 0.0
        terminated = truncated = False
        while not terminated and not truncated:
            legal = [i for i, allowed in enumerate(observation["action_mask"]) if allowed]
            key = state_key(observation)
            values = q.setdefault(key, {})
            for action in legal:
                values.setdefault(action, 0.0)
            if rng.random() < epsilon:
                action = rng.choice(legal)
            else:
                action = max(legal, key=lambda candidate: values[candidate])
            next_observation, reward, terminated, truncated, info = env.step(action)
            next_legal = [i for i, allowed in enumerate(next_observation["action_mask"]) if allowed]
            next_values = q.setdefault(state_key(next_observation), {})
            for next_action in next_legal:
                next_values.setdefault(next_action, 0.0)
            target = reward + (gamma * max(next_values.values(), default=0.0)
                               if not terminated and not truncated else 0.0)
            values[action] += alpha * (target - values[action])
            total += reward
            observation = next_observation
        board = set(env._cards(4) + env._cards(8))
        success = set(info["target_endboard"]).issubset(board)
        history.append((total, success, info["steps"]))
        epsilon = max(epsilon_min, epsilon * epsilon_decay)
        if (episode + 1) % max(1, episodes // 10) == 0:
            window = history[-max(1, min(20, len(history))):]
            print(json.dumps({
                "episode": episode + 1,
                "epsilon": round(epsilon, 4),
                "mean_reward": round(sum(item[0] for item in window) / len(window), 3),
                "mean_steps": round(sum(item[2] for item in window) / len(window), 2),
                "success_rate": round(sum(item[1] for item in window) / len(window), 3),
                "states": len(q),
            }))
    return q


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    train(args.episodes, args.seed)
