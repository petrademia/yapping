import struct
from pathlib import Path
import json

def parse_replay(replay_path: Path):
    with open(replay_path, "rb") as f:
        data = f.read()

    print(f"File size: {len(data)} bytes")
    print("Header Hex:")
    # Print first 256 bytes to see what we are dealing with
    hex_str = " ".join(f"{b:02x}" for b in data[:256])
    print(hex_str)

    # Try to see if it's plaintext JSON (sometimes .yrp3d is just renamed JSON or base64)
    try:
        text = data[:512].decode('utf-8')
        print("First 512 chars as text:")
        print(text)
    except Exception:
        print("Not valid UTF-8 text.")
    
if __name__ == "__main__":
    replay_file = Path(r"c:\Users\petrus\Projects\yapping\scripture\replays\rep.yrp3d")
    if replay_file.exists():
        parse_replay(replay_file)
    else:
        print("File not found.")
