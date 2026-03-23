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

print("Engine gave hand:", hand)

# Let's run _get_hand_from_obs manually
cards = obs.get("cards_")
arr = np.asarray(cards[0], dtype=np.uint8)
loc_col, ctrl_col = 2, 4
in_hand = (arr[:, loc_col] == 2) & (arr[:, ctrl_col] == 0)
hand_rows = np.where(in_hand)[0][:5]
print("hand rows:", hand_rows)
for row in hand_rows:
    v0 = int(arr[row, 0])
    v1 = int(arr[row, 1])
    cid = v0 * 256 + v1
    print(f"Row {row}: v0={v0}, v1={v1}, cid={cid}")
