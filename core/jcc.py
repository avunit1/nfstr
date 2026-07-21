"""
core/jcc.py
Generic helpers for the two things this project ever needs to do to an
x86 conditional jump: invert the condition, or force it to always be
taken (convert to an unconditional jump).

Both operations *read the live bytes first* and detect whether the
instruction is the short form (opcode 0x70-0x7F + 1-byte displacement)
or the near form (0x0F 0x80-0x8F + 4-byte displacement) rather than
trusting a hardcoded assumption from the signature DB. This matters:
the same logical branch can be assembled as either form depending on
how far away the target label ended up, and get it wrong -> the game
crashes almost immediately.

x86 condition codes always come in true/false pairs that differ only in
the low bit of the condition nibble (e.g. JE=0x74/JNE=0x75,
JA=0x0F87/JBE=0x0F86), so "invert" is always exactly `opcode_byte ^= 1`
-- no lookup table needed.

"Force unconditional" re-derives the jump target from the *original*
encoding's own displacement and instruction length, then re-encodes a
plain JMP to that same target using the correct rel8/rel32 math for the
*new* instruction's length. This is the same thing Cheat Engine's own
assembler does when a script writes `jmp <label>` over a conditional
jump -- reusing the raw displacement bytes as-is (as an early draft of
this project mistakenly did) silently computes the wrong target,
because JMP and Jcc encodings of different lengths measure their
displacement from different points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class JccInfo:
    form: str          # "short" | "near"
    total_len: int      # 2 or 6
    opcode_pos: int      # index of the byte whose LSB encodes true/false


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
    """Returns replacement bytes, same length as the original instruction
    (padded with NOP if the new JMP encodes shorter than the Jcc it
    replaces), that unconditionally jump to wherever the original Jcc
    would have jumped."""
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
            return None  # target too far for a short jmp; caller should use near form path instead
        return bytes([0xEB, new_disp & 0xFF])

    disp = int.from_bytes(live_bytes[2:6], "little", signed=True)
    target = instr_addr + old_len + disp
    new_disp = target - (instr_addr + 5)
    out = bytes([0xE9]) + (new_disp & 0xFFFFFFFF).to_bytes(4, "little")
    out += b"\x90" * (old_len - len(out))
    return out
