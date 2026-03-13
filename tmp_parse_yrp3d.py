import struct
from pathlib import Path

def parse_yrp3d(replay_path: Path):
    with open(replay_path, "rb") as f:
        data = f.read()

    # The file starts with:
    # 04 12 00 00 00 00 05 40 1f 00 00 00 ...
    # This might not be LZMA. It might be LZ4 or just raw binary structs.
    # Actually, yrp2b in the strings output suggests it is a specific format.
    print(f"File size: {len(data)}")
    
    # Try finding the 'yrp2b' string
    idx = data.find(b'yrp2b')
    if idx != -1:
        print(f"Found yrp2b signature at offset {idx}")
        # The data after this might be LZMA, LZ4, or JSON
        # Usually Unity binary serializer or MessagePack
        try:
            print("ypr2b nearby:")
            print(data[idx-16:idx+32])
        except Exception:
            pass
            
if __name__ == "__main__":
    replay_file = Path(r"c:\Users\petrus\Projects\yapping\scripture\replays\rep.yrp3d")
    parse_yrp3d(replay_file)
