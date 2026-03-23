import sys
from pathlib import Path
import numpy as np

yapping_root = Path(__file__).resolve().parent
sys.path.insert(0, str(yapping_root))

from engine.environment import create_env

deck_path = yapping_root / "vendor/ygo-env/assets/deck/Branded.ydk"
ygo_root = yapping_root / "vendor/ygo-env"

wrapper = create_env(deck_path, ygo_root)
obs, hand, legal = wrapper.reset()

c = obs["cards_"][0]
print("Card 55 full array:", c[55])
