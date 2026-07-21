"""
core/scanner.py
Array-of-bytes (AOB) signature scanning -- the mechanism that makes this
tool version-independent. Same idea as Cheat Engine's aobscan(): search a
memory range for a byte pattern where some bytes are wildcarded ("??"),
and treat a *unique* hit as trustworthy.

Two scanners are provided:

  AOBScanner        - scans a single, known region (typically the game's
                       main module). This is what signature resolution
                       uses on every attach.

  LiveScanner        - a general-purpose "first scan / next scan" tool,
                       modelled on Cheat Engine's manual workflow, for the
                       handful of features that genuinely cannot be
                       reduced to a fixed offset (heap-allocated gameplay
                       objects such as the currently-loaded car struct).
                       See features/ for how this is used interactively.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Iterable, Optional


PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_IMAGE = 0x1000000


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


def parse_pattern(pattern_str: str) -> tuple[bytes, bytes]:
    """'8A 48 40 ?? 43 08' -> (bytes_with_0_at_wildcards, mask_0xFF_where_fixed)"""
    parts = pattern_str.strip().split()
    pat = bytearray()
    mask = bytearray()
    for p in parts:
        if p in ("??", "?"):
            pat.append(0x00)
            mask.append(0x00)
        else:
            pat.append(int(p, 16))
            mask.append(0xFF)
    return bytes(pat), bytes(mask)


def pattern_quality(pattern_str: str) -> tuple[int, int]:
    parts = pattern_str.strip().split()
    total = len(parts)
    fixed = sum(1 for p in parts if p not in ("??", "?"))
    return fixed, total


class AOBScanner:
    """Scans an explicit [base, base+size) window (normally the game module)."""

    CHUNK = 1 << 16  # 64 KB read chunks, keeps peak memory low
    MIN_FIXED_BYTES = 4
    MIN_TOTAL_BYTES = 5

    def __init__(self, process_handle: int):
        self.handle = process_handle

    def scan(self, base: int, size: int, pattern_str: str,
              max_hits: int = 8) -> list[int]:
        fixed, total = pattern_quality(pattern_str)
        if fixed < self.MIN_FIXED_BYTES or total < self.MIN_TOTAL_BYTES:
            return []  # too weak a pattern to trust -- caller should use RVA fallback

        pat, mask = parse_pattern(pattern_str)
        exact = all(b == 0xFF for b in mask)
        plen = len(pat)
        hits: list[int] = []

        # Overlap chunk boundaries by (plen - 1) bytes so we never miss a
        # match that straddles a chunk edge.
        overlap = plen - 1
        offset = 0
        prev_tail = b""
        while offset < size:
            to_read = min(self.CHUNK, size - offset)
            buf = ctypes.create_string_buffer(to_read)
            read = ctypes.c_size_t(0)
            ok = ctypes.windll.kernel32.ReadProcessMemory(
                self.handle, ctypes.c_void_p(base + offset), buf, to_read,
                ctypes.byref(read),
            )
            data = (prev_tail + buf.raw[:read.value]) if ok else b""
            chunk_start = base + offset - len(prev_tail)

            if data:
                i = 0
                end = len(data) - plen + 1
                while i < end:
                    if exact:
                        idx = data.find(pat, i)
                        if idx == -1:
                            break
                        hits.append(chunk_start + idx)
                        i = idx + 1
                    else:
                        if all((data[i + j] & mask[j]) == pat[j] for j in range(plen)):
                            hits.append(chunk_start + i)
                        i += 1
                    if len(hits) >= max_hits:
                        return hits

            prev_tail = data[-overlap:] if overlap > 0 and data else b""
            offset += to_read

        return hits

    def scan_unique(self, base: int, size: int, pattern_str: str) -> Optional[int]:
        hits = self.scan(base, size, pattern_str, max_hits=2)
        return hits[0] if len(hits) == 1 else None


def enum_regions(process_handle: int,
                   protect_filter=None,
                   type_filter=None,
                   min_addr: int = 0x00010000,
                   max_addr: int = 0x7FFEFFFF) -> Iterable[tuple[int, int, int, int]]:
    """Yield (base, size, protect, type) for committed regions in range,
    optionally filtered. Used by LiveScanner for full-process scans."""
    addr = min_addr
    mbi = MEMORY_BASIC_INFORMATION()
    VirtualQueryEx = ctypes.windll.kernel32.VirtualQueryEx
    while addr < max_addr:
        res = VirtualQueryEx(process_handle, ctypes.c_void_p(addr), ctypes.byref(mbi),
                              ctypes.sizeof(mbi))
        if res == 0:
            break
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize
        if size <= 0:
            break
        if (mbi.State == MEM_COMMIT
                and not (mbi.Protect & PAGE_NOACCESS)
                and not (mbi.Protect & PAGE_GUARD)
                and (protect_filter is None or (mbi.Protect & protect_filter))
                and (type_filter is None or mbi.Type == type_filter)):
            yield (base, size, mbi.Protect, mbi.Type)
        addr = base + size
    return


@dataclass
class ScanResult:
    address: int
    value: bytes


class LiveScanner:
    """
    CE-style 'first scan' + 'next scan (filter to changed/same/specific)'.
    Intended for the small set of features that live on the heap and move
    around between play sessions (see the Research notes ported into
    features/vehicle.py) -- the user performs the same in-game steps the
    community documented, and this class narrows down candidate addresses
    the same way Cheat Engine's scanner would.
    """

    def __init__(self, process_handle: int):
        self.handle = process_handle
        self.results: list[int] = []
        self._value_len = 0

    def first_scan(self, pattern_str: str, private_only: bool = True,
                    max_hits: int = 20000) -> int:
        pat, mask = parse_pattern(pattern_str)
        self._value_len = len(pat)
        exact = all(b == 0xFF for b in mask)
        found: list[int] = []
        type_filter = MEM_PRIVATE if private_only else None
        for base, size, protect, _type in enum_regions(self.handle, type_filter=type_filter):
            if size > (64 << 20):  # skip absurdly large single regions (safety valve)
                continue
            buf = ctypes.create_string_buffer(size)
            read = ctypes.c_size_t(0)
            ok = ctypes.windll.kernel32.ReadProcessMemory(
                self.handle, ctypes.c_void_p(base), buf, size, ctypes.byref(read))
            if not ok:
                continue
            data = buf.raw[:read.value]
            i, end = 0, len(data) - len(pat) + 1
            while i < end:
                if exact:
                    idx = data.find(pat, i)
                    if idx == -1:
                        break
                    found.append(base + idx)
                    i = idx + 1
                else:
                    if all((data[i + j] & mask[j]) == pat[j] for j in range(len(pat))):
                        found.append(base + i)
                    i += 1
                if len(found) >= max_hits:
                    self.results = found
                    return len(found)
        self.results = found
        return len(found)

    def read_current(self, address: int) -> Optional[bytes]:
        buf = ctypes.create_string_buffer(self._value_len)
        read = ctypes.c_size_t(0)
        ok = ctypes.windll.kernel32.ReadProcessMemory(
            self.handle, ctypes.c_void_p(address), buf, self._value_len, ctypes.byref(read))
        return buf.raw if ok else None

    def next_scan_changed(self, previous_values: dict[int, bytes]) -> int:
        kept = []
        for addr in self.results:
            cur = self.read_current(addr)
            if cur is not None and cur != previous_values.get(addr):
                kept.append(addr)
        self.results = kept
        return len(kept)

    def next_scan_equals(self, value_pattern: str) -> int:
        pat, mask = parse_pattern(value_pattern)
        kept = []
        for addr in self.results:
            cur = self.read_current(addr)
            if cur is None:
                continue
            if all((cur[j] & mask[j]) == pat[j] for j in range(len(pat))):
                kept.append(addr)
        self.results = kept
        return len(kept)

    def snapshot(self) -> dict[int, bytes]:
        return {a: self.read_current(a) for a in self.results}
