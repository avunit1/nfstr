from __future__ import annotations

import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from core.memory import SafeMemory
from core.codecave import CodeCaveEngine
from core.resolver import SignatureResolver
from core import jcc


LogFn = Callable[[str], None]


class FeatureEngine:
    def __init__(self, resolver: SignatureResolver, mem: SafeMemory,
                  cave: CodeCaveEngine, all_signatures: Optional[dict] = None,
                  log: Optional[LogFn] = None):
        self.resolver = resolver
        self.mem = mem
        self.cave = cave
        self.all_signatures = all_signatures or {}
        self.log = log or (lambda msg: None)
        self._on: set[str] = set()
        self._freeze_values: dict[str, bytes] = {}
        self._cave_freeze: dict[str, dict] = {}
        self._freeze_thread: Optional[threading.Thread] = None
        self._freeze_stop = threading.Event()
        self._freeze_interval = 0.25
        self._lock = threading.Lock()


    def is_on(self, sig_id: str) -> bool:
        return sig_id in self._on

    def enable(self, sig: dict, **kwargs) -> bool:
        sid = sig["id"]
        patch_type = sig["patch_type"]


        if patch_type == "cave_field_freeze":
            ok = self._do_cave_field_freeze_start(sig, **kwargs)
            companion_id = sig.get("companion")
            if ok and companion_id:
                companion = self.all_signatures.get(companion_id)
                if companion:
                    self._do_cave_field_freeze_start(companion, value=1)
                    self._on.add(companion_id)
            if ok:
                self._on.add(sid)
            self.log(f"[{sid}] enable -> {'OK' if ok else 'FAILED'}")
            return ok

        addr = self.resolver.get(sid)
        if addr is None:
            self.log(f"[{sid}] cannot enable: address not resolved/verified")
            return False

        ok = False
        try:
            if patch_type == "nop":
                ok = self._do_nop(sig, addr, on=True)
            elif patch_type == "byte_write":
                ok = self._do_byte_write(sig, addr, on=True)
            elif patch_type == "jcc_invert":
                ok = self._do_jcc_invert(sig, addr)
            elif patch_type == "jcc_force_jmp":
                ok = self._do_jcc_force_jmp(sig, addr)
            elif patch_type == "codecave":
                ok = self._do_codecave(sig, addr, on=True, **kwargs)
            elif patch_type == "pointer_write":
                ok = self._do_pointer_write(sig, addr, **kwargs)
            elif patch_type == "pointer_toggle":
                ok = self._do_pointer_toggle(sig, addr, on=True)
            elif patch_type == "freeze":
                ok = self._do_freeze_start(sig, addr, **kwargs)
            else:
                self.log(f"[{sid}] unknown patch_type {patch_type!r}")
        except Exception as e:
            self.log(f"[{sid}] enable() raised {e!r}")
            ok = False

        if ok and patch_type not in ("pointer_write",):
            self._on.add(sid)
        self.log(f"[{sid}] enable -> {'OK' if ok else 'FAILED'}")
        return ok

    def disable(self, sig: dict) -> bool:
        sid = sig["id"]
        patch_type = sig["patch_type"]

        if patch_type == "cave_field_freeze":
            ok = self._do_cave_field_freeze_stop(sig)
            companion_id = sig.get("companion")
            if companion_id:
                companion = self.all_signatures.get(companion_id)
                if companion:
                    self._do_cave_field_freeze_stop(companion)
                    self._on.discard(companion_id)
            self._on.discard(sid)
            self.log(f"[{sid}] disable -> {'OK' if ok else 'FAILED'}")
            return ok

        addr = self.resolver.get(sid)
        ok = False
        try:
            if patch_type == "nop":
                ok = self.mem.restore(addr) if addr else False
            elif patch_type == "byte_write":
                ok = self.mem.restore(addr) if addr else False
            elif patch_type in ("jcc_invert", "jcc_force_jmp"):
                ok = self.mem.restore(addr) if addr else False
            elif patch_type == "codecave":
                ok = self.cave.uninstall(sid)
            elif patch_type == "pointer_toggle":
                ok = self._do_pointer_toggle(sig, addr, on=False)
            elif patch_type == "freeze":
                ok = self._do_freeze_stop(sig)
            else:
                ok = True
        except Exception as e:
            self.log(f"[{sid}] disable() raised {e!r}")
            ok = False

        self._on.discard(sid)
        self.log(f"[{sid}] disable -> {'OK' if ok else 'FAILED'}")
        return ok

    def toggle(self, sig: dict, on: bool, **kwargs) -> bool:
        return self.enable(sig, **kwargs) if on else self.disable(sig)


    def _do_nop(self, sig, addr, on: bool) -> bool:
        length = sig["hook_len"]
        if on:
            return self.mem.write_bytes(addr, b"\x90" * length)
        return self.mem.restore(addr)

    def _do_byte_write(self, sig, addr, on: bool) -> bool:
        data = bytes.fromhex(sig["enabled_bytes"] if on else sig.get("disabled_bytes", ""))
        if not data:
            return self.mem.restore(addr)
        return self.mem.write_bytes(addr, data)

    def _do_jcc_invert(self, sig, addr) -> bool:
        current = self.mem.read_bytes(addr, 6)
        if current is None:
            return False
        new_bytes = jcc.invert_condition(current)
        if new_bytes is None:
            self.log(f"[{sig['id']}] bytes at {hex(addr)} don't look like a Jcc "
                      f"instruction ({current[:2].hex()}...) -- refusing to patch")
            return False
        return self.mem.write_bytes(addr, new_bytes)

    def _do_jcc_force_jmp(self, sig, addr) -> bool:
        current = self.mem.read_bytes(addr, 6)
        if current is None:
            return False
        new_bytes = jcc.force_unconditional(current, addr)
        if new_bytes is None:
            self.log(f"[{sig['id']}] bytes at {hex(addr)} don't look like a Jcc "
                      f"instruction, or target is out of range -- refusing to patch")
            return False
        return self.mem.write_bytes(addr, new_bytes)

    def _do_codecave(self, sig, addr, on: bool, value: Optional[float] = None) -> bool:
        if not on:
            return self.cave.uninstall(sig["id"])
        body = bytearray(bytes.fromhex(sig["cave_body"]))
        if value is not None and sig.get("value_offset") is not None:
            fmt = "<f" if sig.get("value_type") == "float" else "<i"
            packed = struct.pack(fmt, value)
            off = sig["value_offset"]
            body[off:off + len(packed)] = packed
        expected = bytes.fromhex(sig["verify_bytes"]) if sig.get("verify_bytes") else None
        return self.cave.install(
            key=sig["id"], hook_addr=addr, hook_len=sig["hook_len"],
            cave_body=bytes(body), return_jmp_offset=sig["return_jmp_offset"],
            expected_hook_bytes=expected,
            data_slot_size=sig.get("data_slot_size", 0),
        )

    def _do_cave_field_freeze_start(self, sig, value: float = 0.0) -> bool:
        ref_id = sig["cave_ref"]
        ref_sig = self.all_signatures.get(ref_id)
        if ref_sig is None:
            self.log(f"[{sig['id']}] unknown cave_ref {ref_id!r}")
            return False
        if not self.cave.is_installed(ref_id):
            ref_addr = self.resolver.get(ref_id)
            if ref_addr is None:
                self.log(f"[{sig['id']}] referenced cave {ref_id} has no resolved address")
                return False
            if not self._do_codecave(ref_sig, ref_addr, on=True):
                self.log(f"[{sig['id']}] failed to install referenced cave {ref_id}")
                return False
        value_type = sig.get("value_type", "float")
        packed = struct.pack("<f" if value_type == "float" else "<i",
                              value if value_type == "float" else int(value))
        with self._lock:
            self._cave_freeze[sig["id"]] = dict(
                cave_ref=ref_id, field_offset=sig["field_offset"], packed=packed,
            )
        self._ensure_freeze_thread()
        return True

    def _do_cave_field_freeze_stop(self, sig) -> bool:
        with self._lock:
            self._cave_freeze.pop(sig["id"], None)
        return True

    def _do_pointer_toggle(self, sig, addr, on: bool) -> bool:
        value = sig["on_value"] if on else sig["off_value"]
        return self._do_pointer_write(sig, addr, value=value, value_type=sig.get("value_type", "u8"))

    def _do_pointer_write(self, sig, addr, value: int = 0, value_type: str = "u32") -> bool:
        offsets = sig.get("offsets", [])
        target = self.mem.read_pointer_chain(addr, offsets) if offsets else addr
        if target is None:
            return False
        if value_type == "u8":
            return self.mem.write_u8(target, value)
        if value_type == "u32":
            return self.mem.write_u32(target, value)
        if value_type == "float":
            return self.mem.write_float(target, value)
        if value_type == "bytes4":
            return self.mem.write_bytes(target, struct.pack("<I", value))
        return False

    def _do_freeze_start(self, sig, addr, value: int = 0, value_type: str = "u32") -> bool:
        with self._lock:
            packed = (struct.pack("<f", value) if value_type == "float"
                       else struct.pack("<I", value & 0xFFFFFFFF))
            self._freeze_values[sig["id"]] = packed
        self._ensure_freeze_thread()
        return True

    def _do_freeze_stop(self, sig) -> bool:
        with self._lock:
            self._freeze_values.pop(sig["id"], None)
        return True

    def _ensure_freeze_thread(self):
        if self._freeze_thread and self._freeze_thread.is_alive():
            return
        self._freeze_stop.clear()

        def loop():
            while not self._freeze_stop.is_set():
                with self._lock:
                    items = list(self._freeze_values.items())
                    cave_items = list(self._cave_freeze.items())
                for sid, packed in items:
                    addr = self.resolver.get(sid)
                    if addr is not None:
                        self.mem.write_bytes(addr, packed, remember=False)
                for sid, info in cave_items:
                    ptr = self.cave.read_data_pointer(info["cave_ref"])
                    if ptr is not None:
                        target = ptr + info["field_offset"]
                        self.mem.write_bytes(target, info["packed"], remember=False)
                time.sleep(self._freeze_interval)

        self._freeze_thread = threading.Thread(target=loop, daemon=True)
        self._freeze_thread.start()

    def shutdown(self):
        self._freeze_stop.set()
        with self._lock:
            self._freeze_values.clear()
            self._cave_freeze.clear()
        self.cave.uninstall_all()
        self.mem.restore_all()
