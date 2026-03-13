import zlib
import gzip
from pathlib import Path

def parse_yrp3d(replay_path: Path):
    with open(replay_path, "rb") as f:
        data = f.read()
    
    # Try zlib (YGO Omega uses zlib for some files? Or maybe standard yrp3d is just bzip2?)
    for offset in range(32):
        try:
            decompressed = zlib.decompress(data[offset:])
            print(f"SUCCESS zlib! Offset {offset}, unpacked {len(decompressed)} bytes")
            return
        except Exception:
            pass

    # Try gzip
    for offset in range(32):
        try:
            decompressed = gzip.decompress(data[offset:])
            print(f"SUCCESS gzip! Offset {offset}, unpacked {len(decompressed)} bytes")
            return
        except Exception:
            pass
            
    # Try bz2
    import bz2
    for offset in range(32):
        try:
            decompressed = bz2.decompress(data[offset:])
            print(f"SUCCESS bz2! Offset {offset}, unpacked {len(decompressed)} bytes")
            return
        except Exception:
            pass
            
    print("All decompression attempts failed.")

if __name__ == "__main__":
    replay_file = Path(r"c:\Users\petrus\Projects\yapping\scripture\replays\rep.yrp3d")
    parse_yrp3d(replay_file)
