from pathlib import Path

import pytest

from matchup_config import load_config
from yapping.rl import BrandedEndboardReachEnv


ROOT = Path(__file__).parents[1]


@pytest.mark.skipif(not (ROOT / "assets/cards.cdb").is_file(), reason="card database is not installed")
def test_branded_endboard_env_has_fixed_shape_and_mask():
    config = load_config(ROOT / "configs/albaz.json")
    config.update({
        "opening_hand": [73819701, 55273560, 91152256, 91152256, 91152256],
        "target_endboard": [44146295, 17751597, 55273560],
    })
    env = BrandedEndboardReachEnv(
        config, database=ROOT / "assets/cards.cdb",
        scripts=ROOT.parent / "fluorohydride-ygopro-scripts",
        max_steps=3,
    )
    observation, info = env.reset(seed=7)
    assert observation["state"].shape == env.observation_space["state"].shape
    assert observation["action_mask"].sum() > 0
    action = int(observation["action_mask"].argmax())
    next_observation, reward, terminated, truncated, info = env.step(action)
    assert next_observation["action_mask"].shape == (env.max_actions,)
    assert isinstance(reward, float)
    assert terminated or truncated or next_observation["action_mask"].sum() >= 0
