"""Run a small, inspectable masked Q-learning experiment."""

import argparse
import json
import random
import sqlite3
from pathlib import Path

from matchup_config import load_config
from yapping.rl import BrandedEndboardReachEnv


ROOT = Path(__file__).parents[1]


def state_key(observation):
    return observation["state"].tobytes()


def card_names(database):
    with sqlite3.connect(database) as connection:
        return {card_id: name for card_id, name in
                connection.execute("SELECT id, name FROM texts")}


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
    names = card_names(ROOT / "assets/cards.cdb")
    q = {}
    rng = random.Random(seed)
    history = []
    best = None
    episode = 0
    try:
      while episodes == 0 or episode < episodes:
        episode += 1
        observation, _ = env.reset(seed=seed + episode)
        total = 0.0
        trajectory = []
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
            descriptor = dict(env._decision["actions"][action])
            next_observation, reward, terminated, truncated, info = env.step(action)
            trajectory.append({
                "action_index": action,
                "kind": descriptor["kind"],
                "card_id": descriptor["card"],
            })
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
        if best is None or (success, total, -info["steps"]) > (
                best["success"], best["reward"], -best["steps"]):
            best = {"episode": episode, "success": success, "reward": total,
                    "steps": info["steps"], "trajectory": trajectory,
                    "endboard": sorted(board)}
        history.append((total, success, info["steps"]))
        epsilon = max(epsilon_min, epsilon * epsilon_decay)
        interval = max(1, (episodes // 10) if episodes else 20)
        if episode % interval == 0:
            window = history[-max(1, min(20, len(history))):]
            target = set(config["target_endboard"])
            best_board = set(best["endboard"])
            target_cards = sorted(target & best_board)
            print(json.dumps({
                "episode": episode,
                "epsilon": round(epsilon, 4),
                "mean_reward": round(sum(item[0] for item in window) / len(window), 3),
                "mean_steps": round(sum(item[2] for item in window) / len(window), 2),
                "success_rate": round(sum(item[1] for item in window) / len(window), 3),
                "states": len(q),
                "best_episode": best["episode"],
                "best_reward": round(best["reward"], 3),
                "best_success": best["success"],
                "best_steps": best["steps"],
                "best_target_cards": [
                    {"card_id": card_id, "card_name": names.get(card_id, str(card_id))}
                    for card_id in target_cards
                ],
            }))
    except KeyboardInterrupt:
        print(json.dumps({"status": "stopped", "episode": episode}))
    return q, best


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=100,
                        help="episode count; 0 runs until Ctrl-C")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    _, best = train(args.episodes, args.seed)
    names = card_names(ROOT / "assets/cards.cdb")
    print(json.dumps({
        "best_episode": best["episode"],
        "success": best["success"],
        "reward": round(best["reward"], 3),
        "steps": best["steps"],
        "trajectory": [
            ({**step, "card_name": names.get(step["card_id"], str(step["card_id"]))}
             if step["card_id"] else {**step, "card_name": "-"})
            for step in best["trajectory"]
        ],
        "endboard": [
            {"card_id": card_id, "card_name": names.get(card_id, str(card_id))}
            for card_id in best["endboard"]
        ],
    }, indent=2, sort_keys=True))
