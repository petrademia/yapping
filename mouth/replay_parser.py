"""
Basic parser/introspector for .yrp3d replay files.

This is a pragmatic parser: it extracts stable metadata and probes common
compression payloads so replay files can be inspected and compared with DFS
traces. It does not yet implement a full event-by-event decoder.
"""

from __future__ import annotations

import bz2
import gzip
import hashlib
import json
import lzma
import struct
import zlib
from pathlib import Path
from typing import Any


def _u16(data: bytes, off: int) -> int:
    if off + 2 > len(data):
        return 0
    return struct.unpack_from("<H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    if off + 4 > len(data):
        return 0
    return struct.unpack_from("<I", data, off)[0]


def _utf16le_strings(data: bytes, start: int = 0, end: int | None = None, min_chars: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    hi = len(data) if end is None else min(len(data), end)
    i = max(0, start)
    while i + 2 <= hi:
        # seek to start of a UTF-16LE printable sequence: byte, 0x00
        if data[i] in (0x00, 0xFF) or (i + 1 < hi and data[i + 1] != 0x00):
            i += 1
            continue
        j = i
        chars: list[str] = []
        while j + 1 < hi:
            ch = data[j]
            nul = data[j + 1]
            if nul != 0x00:
                break
            if ch == 0x00:
                break
            if 32 <= ch <= 126:
                chars.append(chr(ch))
            else:
                break
            j += 2
        if len(chars) >= min_chars:
            text = "".join(chars)
            out.append({"offset": i, "text": text})
            # skip null terminator if present
            if j + 1 < hi and data[j] == 0x00 and data[j + 1] == 0x00:
                j += 2
            i = j
            continue
        i += 1
    return out


def _bytes_hex(data: bytes, n: int = 64) -> str:
    return " ".join(f"{b:02x}" for b in data[:n])


def _try_decompress(kind: str, buf: bytes) -> bytes | None:
    try:
        if kind == "zlib":
            return zlib.decompress(buf)
        if kind == "gzip":
            return gzip.decompress(buf)
        if kind == "bz2":
            return bz2.decompress(buf)
        if kind == "lzma":
            return lzma.decompress(buf)
    except Exception:
        return None
    return None


def _probe_compressed_payloads(data: bytes, max_offset: int = 256) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    kinds = ("zlib", "gzip", "bz2", "lzma")
    hi = min(max_offset, len(data))
    for off in range(hi):
        chunk = data[off:]
        for kind in kinds:
            out = _try_decompress(kind, chunk)
            if out is None:
                continue
            rec: dict[str, Any] = {
                "offset": off,
                "codec": kind,
                "decompressed_size": len(out),
                "sha256": hashlib.sha256(out).hexdigest(),
                "head_hex": _bytes_hex(out, 32),
            }
            # Try JSON parse as a convenience.
            try:
                obj = json.loads(out.decode("utf-8"))
                rec["json_top_type"] = type(obj).__name__
            except Exception:
                pass
            probes.append(rec)
    # de-duplicate by (codec, sha256)
    seen: set[tuple[str, str]] = set()
    uniq: list[dict[str, Any]] = []
    for p in probes:
        k = (str(p["codec"]), str(p["sha256"]))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq


def _probe_compressed_payloads_in_window(data: bytes, start: int, end: int) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    kinds = ("zlib", "gzip", "bz2", "lzma")
    lo = max(0, start)
    hi = min(len(data), end)
    for off in range(lo, hi):
        chunk = data[off:]
        for kind in kinds:
            out = _try_decompress(kind, chunk)
            if out is None:
                continue
            rec: dict[str, Any] = {
                "offset": off,
                "codec": kind,
                "decompressed_size": len(out),
                "sha256": hashlib.sha256(out).hexdigest(),
                "head_hex": _bytes_hex(out, 32),
            }
            try:
                obj = json.loads(out.decode("utf-8"))
                rec["json_top_type"] = type(obj).__name__
            except Exception:
                pass
            probes.append(rec)
    seen: set[tuple[str, str]] = set()
    uniq: list[dict[str, Any]] = []
    for p in probes:
        k = (str(p["codec"]), str(p["sha256"]))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq


def _payload_ascii_hint(payload: bytes) -> str:
    chars = []
    for b in payload[:64]:
        if 32 <= b <= 126:
            chars.append(chr(b))
        else:
            chars.append(".")
    return "".join(chars)


def _scan_len16_records(buf: bytes, start: int, end: int, max_records: int = 256) -> list[dict[str, Any]]:
    """
    Heuristic parser: [u16 type][u16 len][payload...].
    Stops on invalid bounds/zero len. Returns contiguous records from start.
    """
    recs: list[dict[str, Any]] = []
    off = start
    limit = min(end, len(buf))
    while off + 4 <= limit and len(recs) < max_records:
        typ = _u16(buf, off)
        ln = _u16(buf, off + 2)
        if ln <= 0 or off + 4 + ln > limit:
            break
        payload = buf[off + 4 : off + 4 + ln]
        recs.append(
            {
                "offset": off,
                "type_u16": typ,
                "len_u16": ln,
                "payload_head_hex": _bytes_hex(payload, 24),
                "payload_ascii_hint": _payload_ascii_hint(payload),
            }
        )
        off += 4 + ln
    return recs


def _scan_len32_records(buf: bytes, start: int, end: int, max_records: int = 256) -> list[dict[str, Any]]:
    """
    Heuristic parser: [u32 type][u32 len][payload...].
    Stops on invalid bounds/zero len. Returns contiguous records from start.
    """
    recs: list[dict[str, Any]] = []
    off = start
    limit = min(end, len(buf))
    while off + 8 <= limit and len(recs) < max_records:
        typ = _u32(buf, off)
        ln = _u32(buf, off + 4)
        if ln <= 0 or ln > 1_000_000 or off + 8 + ln > limit:
            break
        payload = buf[off + 8 : off + 8 + ln]
        recs.append(
            {
                "offset": off,
                "type_u32": typ,
                "len_u32": ln,
                "payload_head_hex": _bytes_hex(payload, 24),
                "payload_ascii_hint": _payload_ascii_hint(payload),
            }
        )
        off += 8 + ln
    return recs


def _scan_binary_candidates(buf: bytes, start: int, end: int) -> dict[str, Any]:
    """
    Try several candidate starts/layouts for a trailer chunk and return best-looking streams.
    """
    starts = [start, start + 4, start + 8, start + 12, start + 16, start + 20, start + 24, start + 32]
    out: dict[str, Any] = {"len16_streams": [], "len32_streams": []}
    for s in starts:
        if s >= end:
            continue
        r16 = _scan_len16_records(buf, s, end)
        if len(r16) >= 2:
            out["len16_streams"].append({"start": s, "count": len(r16), "records": r16[:50]})
        r32 = _scan_len32_records(buf, s, end)
        if len(r32) >= 2:
            out["len32_streams"].append({"start": s, "count": len(r32), "records": r32[:50]})
    # Sort by record count desc for quick inspection.
    out["len16_streams"] = sorted(out["len16_streams"], key=lambda x: int(x["count"]), reverse=True)[:5]
    out["len32_streams"] = sorted(out["len32_streams"], key=lambda x: int(x["count"]), reverse=True)[:5]
    return out


def _entropy(block: bytes) -> float:
    if not block:
        return 0.0
    freq = [0] * 256
    for b in block:
        freq[b] += 1
    n = float(len(block))
    ent = 0.0
    import math
    for c in freq:
        if c == 0:
            continue
        p = c / n
        ent -= p * math.log2(p)
    return ent


def _segment_entropy(buf: bytes, start: int, end: int, window: int = 32) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    lo = max(0, start)
    hi = min(len(buf), end)
    i = lo
    while i < hi:
        j = min(hi, i + window)
        block = buf[i:j]
        out.append(
            {
                "offset": i,
                "size": len(block),
                "entropy": round(_entropy(block), 4),
                "hex": _bytes_hex(block, min(16, len(block))),
                "ascii_hint": _payload_ascii_hint(block),
            }
        )
        i = j
    return out


def _scan_fixed_stride_structs(buf: bytes, start: int, end: int) -> dict[str, Any]:
    """
    Inspect trailer as fixed-size records for common strides.
    Returns first few decoded records for each stride.
    """
    strides = (8, 12, 16, 24, 32)
    lo = max(0, start)
    hi = min(len(buf), end)
    out: dict[str, Any] = {}
    for s in strides:
        n = (hi - lo) // s
        if n < 2:
            continue
        recs: list[dict[str, Any]] = []
        for i in range(min(n, 40)):
            off = lo + i * s
            rec = buf[off : off + s]
            u32_vals = []
            u16_vals = []
            # decode little-endian words for quick pattern inspection
            for j in range(0, len(rec) - (len(rec) % 4), 4):
                u32_vals.append(struct.unpack_from("<I", rec, j)[0])
            for j in range(0, len(rec) - (len(rec) % 2), 2):
                u16_vals.append(struct.unpack_from("<H", rec, j)[0])
            recs.append(
                {
                    "offset": off,
                    "hex": _bytes_hex(rec, s),
                    "u32": u32_vals[:6],
                    "u16": u16_vals[:8],
                    "ascii_hint": _payload_ascii_hint(rec),
                }
            )
        out[str(s)] = {"stride": s, "record_count": n, "records": recs}
    return out


def _read_uleb128(buf: bytes, off: int, end: int) -> tuple[int | None, int]:
    """
    Parse unsigned LEB128-like varint from buf[off:end].
    Returns (value, next_off). value=None on failure.
    """
    value = 0
    shift = 0
    i = off
    while i < end and shift <= 63:
        b = buf[i]
        value |= (b & 0x7F) << shift
        i += 1
        if (b & 0x80) == 0:
            return value, i
        shift += 7
    return None, off


def _scan_varints(buf: bytes, start: int, end: int, max_fields: int = 256) -> list[dict[str, Any]]:
    """
    Best-effort varint scanner: reads sequential ULEB128 values.
    """
    out: list[dict[str, Any]] = []
    lo = max(0, start)
    hi = min(len(buf), end)
    i = lo
    while i < hi and len(out) < max_fields:
        val, j = _read_uleb128(buf, i, hi)
        if val is None or j <= i:
            i += 1
            continue
        out.append({"offset": i, "value": int(val), "len": j - i})
        i = j
    return out


def _possible_action_strings(strings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "summon",
        "activate",
        "set",
        "draw",
        "chain",
        "turn",
        "battle",
        "main phase",
        "end phase",
    )
    out: list[dict[str, Any]] = []
    for s in strings:
        txt = str(s.get("text", ""))
        low = txt.lower()
        if any(k in low for k in keys):
            out.append(s)
    return out


def parse_yrp3d(path: str | Path) -> dict[str, Any]:
    p = Path(path).resolve()
    data = p.read_bytes()
    report: dict[str, Any] = {
        "path": str(p),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "head_hex_128": _bytes_hex(data, 128),
        "u16_0": _u16(data, 0),
        "u16_2": _u16(data, 2),
        "u32_0": _u32(data, 0),
        "u32_4": _u32(data, 4),
        "u32_8": _u32(data, 8),
        "u32_12": _u32(data, 12),
        "u32_16": _u32(data, 16),
        "u32_20": _u32(data, 20),
        "u32_24": _u32(data, 24),
        "ascii_markers": {},
    }

    marker_offsets: dict[str, int] = {}
    for marker in (b"yrp1", b"yrp2", b"yrp2b", b"yrp3", b"YRP", b"JSON"):
        idx = data.find(marker)
        if idx != -1:
            key = marker.decode("ascii", errors="ignore")
            report["ascii_markers"][key] = idx
            marker_offsets[key] = idx

    head_strings = _utf16le_strings(data, start=0, end=min(len(data), 4096), min_chars=3)
    all_strings = _utf16le_strings(data, start=0, end=len(data), min_chars=3)
    report["utf16_strings_head"] = head_strings
    report["utf16_strings_all_count"] = len(all_strings)
    report["utf16_action_like_strings"] = _possible_action_strings(all_strings)[:300]
    report["compression_probes"] = _probe_compressed_payloads(data, max_offset=256)

    # If replay marker exists near file end, inspect that trailer/chunk more deeply.
    marker_key = "yrp2b" if "yrp2b" in marker_offsets else ("yrp2" if "yrp2" in marker_offsets else None)
    if marker_key is not None:
        off = marker_offsets[marker_key]
        tail = data[off:]
        report["marker_trailer"] = {
            "marker": marker_key,
            "offset": off,
            "tail_size": len(tail),
            "tail_sha256": hashlib.sha256(tail).hexdigest(),
            "tail_head_hex_64": _bytes_hex(tail, 64),
            "u32_after_marker_0": _u32(data, off + len(marker_key)),
            "u32_after_marker_4": _u32(data, off + len(marker_key) + 4),
            "u32_after_marker_8": _u32(data, off + len(marker_key) + 8),
        }
        report["compression_probes_near_marker"] = _probe_compressed_payloads_in_window(
            data, start=off, end=min(len(data), off + 2048)
        )
        # Heuristic binary record scan on trailer payload (skip marker itself).
        payload_start = off + len(marker_key)
        report["marker_binary_candidates"] = _scan_binary_candidates(
            data,
            start=payload_start,
            end=min(len(data), off + len(tail)),
        )
        report["marker_fixed_stride_candidates"] = _scan_fixed_stride_structs(
            data,
            start=payload_start,
            end=min(len(data), off + len(tail)),
        )
        report["marker_varint_scan"] = _scan_varints(
            data,
            start=payload_start,
            end=min(len(data), off + len(tail)),
            max_fields=512,
        )
        report["marker_entropy_segments"] = _segment_entropy(
            data,
            start=payload_start,
            end=min(len(data), off + len(tail)),
            window=32,
        )
    return report
