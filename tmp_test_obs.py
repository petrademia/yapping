import sys
import os
from pathlib import Path

# Use relative paths so it works in WSL or Windows
yapping_root = Path(__file__).resolve().parent
sys.path.insert(0, str(yapping_root))

from vocal_chords.environment import create_env

deck_path = yapping_root / "vendor/ygo-env/assets/deck/Branded.ydk"
ygo_root = yapping_root / "vendor/ygo-env"

print("Creating env...")
wrapper = create_env(deck_path, ygo_root)
print("Resetting env...")
obs, hand, legal = wrapper.reset()

print("Hand:", hand)
print("Legal:", legal)

print("Obs keys:", obs.keys() if hasattr(obs, "keys") else type(obs))
if hasattr(obs, "get"):
    for k in obs.keys():
        val = obs[k]
        shape = getattr(val, "shape", "no shape")
        print(f"Key: {k}, type: {type(val)}, shape: {shape}")
