from pathlib import Path
from vocal_chords.wrapper import YgoEnvWrapper
import platform

if __name__ == "__main__":
    if platform.system() == "Windows":
        ygo_root = Path(r"c:\Users\petrus\Projects\yapping\vendor\ygo-env")
        deck = Path(r"c:\Users\petrus\Projects\yapping\vendor\ygo-env\assets\deck\Branded.ydk")
    else:
        ygo_root = Path("/mnt/c/Users/petrus/Projects/yapping/vendor/ygo-env")
        deck = Path("/mnt/c/Users/petrus/Projects/yapping/vendor/ygo-env/assets/deck/Branded.ydk")
    
    print("Initializing env...")
    try:
        env = YgoEnvWrapper(deck_path=deck, ygo_env_root=ygo_root, seed=123)
        print("Env initialized!")
        obs, hand, legal = env.reset()
        print("Reset successful!")
        print(f"Hand: {hand}")
        print(f"Legal: {legal}")
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
