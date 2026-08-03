from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class JccInfo:
    form: str
    total_len: int
    opcode_pos: int


def detect_jcc(live_bytes: bytes) -> Optional[JccInfo]:
    if len(live_bytes) >= 2 and 0x70 <= live_bytes[0] <= 0x7F:
        return JccInfo("short", 2, 0)
    if len(live_bytes) >= 6 and live_bytes[0] == 0x0F and 0x80 <= live_bytes[1] <= 0x8F:
        return JccInfo("near", 6, 1)
    return None


def invert_condition(live_bytes: bytes) -> Optional[bytes]:
    info = detect_jcc(live_bytes)
    if info is None:
        return None
    out = bytearray(live_bytes[:info.total_len])
    out[info.opcode_pos] ^= 0x01
    return bytes(out)


def force_unconditional(live_bytes: bytes, instr_addr: int) -> Optional[bytes]:
    info = detect_jcc(live_bytes)
    if info is None:
        return None
    old_len = info.total_len

    if info.form == "short":
        disp = live_bytes[1]
        if disp >= 0x80:
            disp -= 0x100
        target = instr_addr + old_len + disp
        new_disp = target - (instr_addr + 2)
        if not (-128 <= new_disp <= 127):
            return None
        return bytes([0xEB, new_disp & 0xFF])

    disp = int.from_bytes(live_bytes[2:6], "little", signed=True)
    target = instr_addr + old_len + disp
    new_disp = target - (instr_addr + 5)
    out = bytes([0xE9]) + (new_disp & 0xFFFFFFFF).to_bytes(4, "little")
    out += b"\x90" * (old_len - len(out))
    return out
