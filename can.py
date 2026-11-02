"""CAN frame helpers and the SocketCAN `candump -L` log format."""
import re

from .signals import BY_PGN_SA, Signal

BASE_EPOCH = 1_700_000_000.0
_LINE = re.compile(r"\(\s*(\d+\.\d+)\)\s+(\S+)\s+([0-9A-Fa-f]+)#([0-9A-Fa-f]*)")


def make_id(pgn: int, sa: int, prio: int = 6) -> int:
    return (prio << 26) | (pgn << 8) | sa


def split_id(can_id: int):
    return (can_id >> 8) & 0x3FFFF, can_id & 0xFF  # pgn, source address


def encode(sig: Signal, raw: int) -> bytes:
    data = bytearray(b"\xff" * 8)
    data[sig.start:sig.start + sig.length] = raw.to_bytes(sig.length, "little")
    return bytes(data)


def raw_from_value(sig: Signal, value: float) -> int:
    raw = int(round((value - sig.offset) / sig.scale))
    return max(0, min(sig.valid_max, raw))


def decode(can_id: int, data: bytes):
    """Return (signal, raw, value or None, is_error) or None if the frame is unknown."""
    pgn, sa = split_id(can_id)
    sig = BY_PGN_SA.get((pgn, sa))
    if sig is None or len(data) < sig.start + sig.length:
        return None
    raw = int.from_bytes(data[sig.start:sig.start + sig.length], "little")
    if raw > sig.valid_max:
        return sig, raw, None, True
    return sig, raw, raw * sig.scale + sig.offset, False


def format_line(t: float, can_id: int, data: bytes) -> str:
    return f"({t:.6f}) can0 {can_id:08X}#{data.hex().upper()}"


def parse_line(line: str):
    m = _LINE.match(line.strip())
    if not m:
        return None
    return float(m.group(1)), int(m.group(3), 16), bytes.fromhex(m.group(4))


def read_candump(path):
    with open(path) as f:
        return [fr for fr in (parse_line(l) for l in f) if fr]


def write_candump(frames, path):
    with open(path, "w") as f:
        for t, cid, data in frames:
            f.write(format_line(t, cid, data) + "\n")
