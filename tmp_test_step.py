import sys
from pathlib import Path
import numpy as np

yapping_root = Path(__file__).resolve().parent
sys.path.insert(0, str(yapping_root))

from vocal_chords.environment import create_env

deck_path = yapping_root / "vendor/ygo-env/assets/deck/Branded.ydk"
ygo_root = yapping_root / "vendor/ygo-env"

wrapper = create_env(deck_path, ygo_root)
obs, hand, legal = wrapper.reset()

print("Keys:", obs.keys())
print("actions_ shape:", obs["actions_"].shape)
a = obs["actions_"][0]
valid_actions = 0
for i in range(24):
    if np.any(a[i]):
        valid_actions += 1
print("Valid actions count (non-zero in actions_):", valid_actions)

c = obs["cards_"][0]
print("cards_ shape:", c.shape)

in_hand = 0
for i in range(160):
    if np.any(c[i]):
        # index 0,1 are card id, index 2 is location?
        loc = c[i][2]
        ctrl = c[i][4]
        # In ygo, location hand is usually 2. Let's print non-zero cards
        if c[i][2] == 2:
            print(f"Card {i} is in hand, ctrl={ctrl}, id_bytes={c[i][0]},{c[i][1]}")
            in_hand += 1
print("Total cards in hand:", in_hand)
