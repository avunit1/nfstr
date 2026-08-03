from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass
from typing import Optional

from .memory import SafeMemory

log = logging.getLogger("nfstr.codecave")

MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_EXECUTE_READWRITE = 0x40


def rel32_jmp(from_addr: int, to_addr: int) -> bytes:
    disp = (to_addr - (from_addr + 5)) & 0xFFFFFFFF
    return b"\xE9" + disp.to_bytes(4, "little")


@dataclass
class ActiveCave:
    cave_addr: int
    cave_size: int
    hook_addr: int
    hook_len: int
    original_hook_bytes: bytes
    data_addr: Optional[int] = None


class CodeCaveEngine:
    def __init__(self, process_handle: int, mem: SafeMemory):
        self.handle = process_handle
        self.mem = mem
        self._active: dict[str, ActiveCave] = {}

    def _alloc(self, size: int) -> int:
        addr = ctypes.windll.kernel32.VirtualAllocEx(
            self.handle, None, ctypes.c_size_t(size),
            MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE,
        )
        if not addr:
            raise MemoryError("VirtualAllocEx failed in target process")
        return addr

    def _free(self, addr: int):
        ctypes.windll.kernel32.VirtualFreeEx(self.handle, ctypes.c_void_p(addr), 0, MEM_RELEASE)

    def install(self, key: str, hook_addr: int, hook_len: int,
                 cave_body: bytes, return_jmp_offset: int,
                 expected_hook_bytes: Optional[bytes] = None,
                 data_slot_size: int = 0,
                 data_slot_placeholder: bytes = b"\x44\x33\x22\x11") -> bool:
        if key in self._active:
            log.debug("[%s] already installed, skipping", key)
            return True

        if expected_hook_bytes is not None:
            live = self.mem.read_bytes(hook_addr, len(expected_hook_bytes))
            if live != expected_hook_bytes:
                log.warning("[%s] hook site %s bytes mismatch: expected %s got %s -- refusing to patch",
                             key, hex(hook_addr), expected_hook_bytes.hex(),
                             live.hex() if live else None)
                return False

        original_hook_bytes = self.mem.read_bytes(hook_addr, hook_len)
        if original_hook_bytes is None or len(original_hook_bytes) != hook_len:
            log.error("[%s] could not read %d bytes at hook site %s", key, hook_len, hex(hook_addr))
            return False

        data_addr = None
        body = bytearray(cave_body)
        if data_slot_size > 0:
            data_addr = self._alloc(data_slot_size)
            log.debug("[%s] data slot allocated at %s (%d bytes)", key, hex(data_addr), data_slot_size)
            patched_any = False
            search_from = 0
            needle = data_slot_placeholder
            addr_bytes = data_addr.to_bytes(4, "little")
            while True:
                idx = bytes(body).find(needle, search_from)
                if idx == -1:
                    break
                body[idx:idx + 4] = addr_bytes
                search_from = idx + 4
                patched_any = True
            if not patched_any:
                log.error("[%s] data-slot placeholder not found in cave body -- aborting install", key)
                self._free(data_addr)
                return False

        cave_addr = self._alloc(max(len(body), 64))
        log.debug("[%s] cave allocated at %s (%d bytes)", key, hex(cave_addr), len(body))


        return_here = hook_addr + hook_len
        body[return_jmp_offset:return_jmp_offset + 5] = rel32_jmp(
            cave_addr + return_jmp_offset, return_here
        )

        if not self.mem.write_bytes(cave_addr, bytes(body), remember=False):
            log.error("[%s] failed to write cave body to %s", key, hex(cave_addr))
            self._free(cave_addr)
            if data_addr:
                self._free(data_addr)
            return False

        hook_patch = rel32_jmp(hook_addr, cave_addr)
        if hook_len > 5:
            hook_patch += b"\x90" * (hook_len - 5)

        if not self.mem.write_bytes(hook_addr, hook_patch, remember=False):
            log.error("[%s] failed to write hook jmp at %s", key, hex(hook_addr))
            self._free(cave_addr)
            if data_addr:
                self._free(data_addr)
            return False

        self._active[key] = ActiveCave(
            cave_addr=cave_addr, cave_size=len(body),
            hook_addr=hook_addr, hook_len=hook_len,
            original_hook_bytes=original_hook_bytes,
            data_addr=data_addr,
        )
        log.info("[%s] installed: hook=%s cave=%s size=%d%s", key, hex(hook_addr),
                  hex(cave_addr), len(body), f" data_slot={hex(data_addr)}" if data_addr else "")
        return True

    def uninstall(self, key: str) -> bool:
        cave = self._active.pop(key, None)
        if cave is None:
            return False
        ok = self.mem.write_bytes(cave.hook_addr, cave.original_hook_bytes, remember=False)
        self._free(cave.cave_addr)
        if cave.data_addr:
            self._free(cave.data_addr)
        log.info("[%s] uninstalled (restored hook at %s): %s", key, hex(cave.hook_addr), "OK" if ok else "FAILED")
        return ok

    def read_data_pointer(self, key: str) -> Optional[int]:
        cave = self._active.get(key)
        if cave is None or cave.data_addr is None:
            return None
        raw = self.mem.read_bytes(cave.data_addr, 4)
        if raw is None:
            return None
        value = int.from_bytes(raw, "little")
        return value or None

    def is_installed(self, key: str) -> bool:
        return key in self._active

    def uninstall_all(self):
        for key in list(self._active.keys()):
            self.uninstall(key)
