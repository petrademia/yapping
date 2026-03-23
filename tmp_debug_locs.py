import numpy as np
from pathlib import Path
from engine.wrapper import YgoEnvWrapper
from engine.actions import _ACT_NAMES, _ID_TO_MSG
import json

def load_card_id_to_code(ygo_root: Path) -> dict:
    path = ygo_root / "example" / "code_list.txt"
    if not path.is_file(): return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            parts = line.strip().split()
            if parts and parts[0].isdigit(): out[i] = int(parts[0])
    return out

if __name__ == "__main__":
    _HERE = Path(__file__).resolve().parent
    _YGO_ROOT = _HERE / "vendor" / "ygo-env"
    _DECK = _YGO_ROOT / "assets" / "deck" / "Branded.ydk"
    
    env = YgoEnvWrapper(deck_path=_DECK, ygo_env_root=_YGO_ROOT, seed=123)
    cid_map = load_card_id_to_code(_YGO_ROOT)
    
    # Capture raw output
    _ = env.reset()
    raw_obs = env._obs
    print(f"Type of raw_obs: {type(raw_obs)}")
    
    # Try to find the dictionary
    obs_dict = None
    if isinstance(raw_obs, dict):
        obs_dict = raw_obs
    elif isinstance(raw_obs, (list, tuple)):
        print(f"raw_obs is list/tuple of len {len(raw_obs)}")
        if len(raw_obs) > 0 and isinstance(raw_obs[0], dict):
            obs_dict = raw_obs[0]
            print("Found dict at raw_obs[0]")
    
    if obs_dict:
        print(f"Keys in obs_dict: {list(obs_dict.keys())}")
        cards_key = "obs:cards_" if "obs:cards_" in obs_dict else "cards_"
        acts_key = "obs:actions_" if "obs:actions_" in obs_dict else "actions_"
        
        cards = obs_dict.get(cards_key)
        actions = obs_dict.get(acts_key)
        
        if cards is not None:
            arr = np.asarray(cards)
            print(f"Cards shape: {arr.shape}")
            if arr.ndim == 3: arr = arr[0]
            for row in range(arr.shape[0]):
                if arr[row, 4] == 0: # our cards
                    loc = int(arr[row, 2])
                    cid = int(arr[row, 0]) * 256 + int(arr[row, 1])
                    code = cid_map.get(cid, 0)
                    if loc != 1: # exclude deck
                        print(f"  Row {row}: CID {cid} (Code {code}) -> Loc {loc}")
                        if code == 73819701:
                            print(f"  *** WHITE DRAGON FOUND ***")

        if actions is not None:
            arr = np.asarray(actions)
            print(f"Actions shape: {arr.shape}")
            if arr.ndim == 3: arr = arr[0]
            num_options = env._num_options_from_info()
            print(f"Num options from info: {num_options}")
            
            for i in range(num_options or arr.shape[0]):
                feat = arr[i]
                msg_id = int(feat[3])
                if msg_id == 0: continue
                
                act_id = int(feat[4])
                cid = int(feat[1]) * 256 + int(feat[2])
                code = cid_map.get(cid, 0)
                
                msg_name = _ID_TO_MSG.get(msg_id, f"msg{msg_id}")
                act_name = _ACT_NAMES[act_id] if act_id < len(_ACT_NAMES) else f"act{act_id}"
                
                print(f"  Action {i}: {msg_name} | {act_name} | Card Code {code} (feat: {feat})")
    else:
        print("Could not find observation dictionary!")
