"""
core/memory.py
Typed, defensive read/write helpers on top of pymem.

Every write in this project goes through SafeMemory so that:
  1. We can optionally verify the bytes currently at an address match
     what we *expect* before we touch them (protects against patching
     the wrong thing on an unrecognised build).
  2. Every write is remembered so it can be reverted (best-effort) when
     a feature is turned off or the tool exits.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

import pymem


@dataclass
class WriteRecord:
    address: int
    original_bytes: bytes


class SafeMemory:
    def __init__(self, pm: pymem.Pymem):
        self.pm = pm
        self._history: dict[int, WriteRecord] = {}

    # ---- raw ------------------------------------------------------------
    def read_bytes(self, address: int, length: int) -> Optional[bytes]:
        try:
            return self.pm.read_bytes(address, length)
        except Exception:
            return None

    def write_bytes(self, address: int, data: bytes, remember: bool = True) -> bool:
        try:
            if remember and address not in self._history:
                original = self.read_bytes(address, len(data))
                if original is not None:
                    self._history[address] = WriteRecord(address, original)
            self.pm.write_bytes(address, data, len(data))
            return True
        except Exception:
            return False

    # ---- typed convenience ----------------------------------------------
    def read_u8(self, a):  return self._read("B", a)
    def read_i8(self, a):  return self._read("b", a)
    def read_u32(self, a): return self._read("<I", a)
    def read_i32(self, a): return self._read("<i", a)
    def read_float(self, a): return self._read("<f", a)

    def write_u8(self, a, v):  return self.write_bytes(a, struct.pack("B", v & 0xFF))
    def write_i8(self, a, v):  return self.write_bytes(a, struct.pack("b", v))
    def write_u32(self, a, v): return self.write_bytes(a, struct.pack("<I", v & 0xFFFFFFFF))
    def write_i32(self, a, v): return self.write_bytes(a, struct.pack("<i", v))
    def write_float(self, a, v): return self.write_bytes(a, struct.pack("<f", float(v)))

    def _read(self, fmt, address):
        size = struct.calcsize(fmt)
        raw = self.read_bytes(address, size)
        if raw is None or len(raw) != size:
            return None
        return struct.unpack(fmt, raw)[0]

    # ---- pointer chains ---------------------------------------------------
    def read_pointer_chain(self, base_address: int, offsets: list[int]) -> Optional[int]:
        """
        Mimics Cheat Engine's "Address + Offsets" resolution:
        ptr = [base_address]; for each offset but the last: ptr = [ptr+offset]
        final address = ptr + offsets[-1]
        If offsets is empty, returns base_address itself.
        """
        if not offsets:
            return base_address
        ptr = self.read_u32(base_address)
        if ptr is None:
            return None
        for off in offsets[:-1]:
            ptr = self.read_u32(ptr + off)
            if ptr is None:
                return None
        return ptr + offsets[-1]

    # ---- verify / restore --------------------------------------------------
    def verify(self, address: int, expected: bytes) -> bool:
        actual = self.read_bytes(address, len(expected))
        return actual == expected

    def restore(self, address: int) -> bool:
        rec = self._history.pop(address, None)
        if rec is None:
            return False
        try:
            self.pm.write_bytes(rec.address, rec.original_bytes, len(rec.original_bytes))
            return True
        except Exception:
            return False

    def restore_all(self):
        for addr in list(self._history.keys()):
            self.restore(addr)
