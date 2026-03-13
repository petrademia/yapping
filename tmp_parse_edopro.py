import lzma
from pathlib import Path
import struct

def parse_edopro_replay(replay_path: Path):
    with open(replay_path, "rb") as f:
        data = f.read()

    # The user states: LZMA compression after the header (usually the first 32 bytes)
    header_size = 32
    
    # Let's inspect the first 64 bytes to see if there's an LZMA signature around byte 32.
    # Standard LZMA props: 5D 00 00 ...
    
    # Print the bytes around 32
    print("Bytes 24 to 48:")
    print(" ".join(f"{b:02x}" for b in data[24:48]))
    
    # Let's try to decompress starting at various bytes around 32
    for offset in range(24, 40):
        # We can try raw decompression or injecting the uncompressed size
        props = data[offset:offset+5]
        # inject 8 bytes of uncompressed size (-1 = unknown)
        lzma_header = props + b'\xFF'*8
        payload = lzma_header + data[offset+5:]
        try:
            decompressed = lzma.decompress(payload, format=lzma.FORMAT_ALONE)
            print(f"SUCCESS with custom inject! Offset {offset}, unpacked {len(decompressed)} bytes")
            
            out_path = Path("tmp_replay_unpacked.bin")
            out_path.write_bytes(decompressed)
            print(f"Wrote to {out_path}")
            return
        except Exception:
            pass
            
    # Try FORMAT_AUTO just in case it has the full header including uncompressed size
    for offset in range(24, 40):
        try:
            decompressed = lzma.decompress(data[offset:])
            print(f"SUCCESS FORMAT_AUTO! Offset {offset}, unpacked {len(decompressed)} bytes")
            return
        except Exception:
            pass
            
    print("Could not decompress with Edopro 32-byte header offset.")

if __name__ == "__main__":
    replay_file = Path(r"c:\Users\petrus\Projects\yapping\scripture\replays\rep.yrp3d")
    parse_edopro_replay(replay_file)
