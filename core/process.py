"""
core/process.py
Process discovery and attachment for NFS: The Run.

Design notes
------------
- We attach by process *name* (several known executable names, see
  PROCESS_NAMES) rather than assuming a fixed install path, so Steam,
  Origin, and standalone/cracked copies all work the same way.
- We never assume a fixed module base address. NFS: The Run is a 32-bit,
  non-ASLR (or ASLR-tolerant via delta computation) executable; we always
  ask Windows for the *actual* base via Module32First/Next and compute an
  "ASLR delta" against the historical reference base (0x00400000, the
  address the original _mRally2 Cheat Engine table was captured at).
  Every address resolved elsewhere in this project is expressed as
  base + RVA, never as a bare historical absolute address, so a shifted
  load address does not break anything.
- SHA256 of the on-disk executable is used purely as a *cache key*
  (see core/cache.py) so that once a build has been calibrated, future
  launches skip the AOB scan and jump straight to known-good addresses.
  It is never required for the tool to function - if it's a hash we've
  never seen, we just fall back to a full scan.
"""

from __future__ import annotations

import ctypes
import hashlib
import logging
import os
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional

import pymem
import pymem.process

log = logging.getLogger("nfstr.process")


# Reference image base the master Cheat Engine table's absolute addresses
# were captured against. Every historical "abs_fallback" address in the
# signature DB is stored as (this_value_subtracted) i.e. as an RVA.
REFERENCE_IMAGE_BASE = 0x00400000

# Known process names across storefronts / cracked builds. Extend this list
# freely -- it costs nothing to check a few extra names.
PROCESS_NAMES = [
    "Need for Speed The Run.exe",
    "Need For Speed The Run.exe",
    "NeedForSpeedTheRun.exe",
    "nfs_run.exe",
    "NFS13.exe",
    "nfs13.exe",
]

MAIN_MODULE_CANDIDATES = PROCESS_NAMES  # module name == exe name for this game


@dataclass
class TargetProcess:
    pm: pymem.Pymem
    pid: int
    process_name: str
    module_name: str
    base: int
    size: int
    delta: int              # base - REFERENCE_IMAGE_BASE
    exe_path: Optional[str]
    sha256: Optional[str]

    def rva(self, address: int) -> int:
        """Convert a live absolute address back to an RVA (address - base)."""
        return address - self.base

    def addr(self, rva: int) -> int:
        """Convert an RVA into a live absolute address in this process.
        Every address in data/signatures.json ('historical_rva') is
        already stored relative to the module base (REFERENCE_IMAGE_BASE),
        so this is the *only* conversion ever needed: base + rva. There
        used to also be a ref_addr() that took a raw historical absolute
        address and re-derived the same result a different way -- it was
        removed because having two ways to reach the same address was
        exactly how a base+rva value ended up getting run through the
        wrong one and silently coming out offset by REFERENCE_IMAGE_BASE."""
        return self.base + rva


def _sha256_of_file(path: str, chunk: int = 1 << 20) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                buf = f.read(chunk)
                if not buf:
                    break
                h.update(buf)
        return h.hexdigest()
    except OSError:
        return None


def find_pid_by_names(names) -> Optional[tuple[int, str]]:
    """Return (pid, matched_process_name) for the first running process
    whose name matches one of `names` (case-insensitive)."""
    try:
        import psutil  # optional, nicer enumeration; fall back if missing
        wanted = {n.lower() for n in names}
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pname = proc.info.get("name") or ""
            except Exception:
                continue
            if pname.lower() in wanted:
                return proc.info["pid"], pname
        return None
    except ImportError:
        pass

    # Fallback: raw CreateToolhelp32Snapshot walk (no extra dependency).
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return None
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        wanted = {n.lower() for n in names}
        found = None
        if kernel32.Process32First(snap, ctypes.byref(entry)):
            while True:
                exe = entry.szExeFile.decode(errors="ignore")
                if exe.lower() in wanted:
                    found = (entry.th32ProcessID, exe)
                    break
                if not kernel32.Process32Next(snap, ctypes.byref(entry)):
                    break
        return found
    finally:
        kernel32.CloseHandle(snap)


def attach(names=None, timeout: float = 0.0, poll_interval: float = 1.0) -> TargetProcess:
    """
    Attach to the game process.

    timeout=0 means "try once and raise if not found". A positive timeout
    polls every `poll_interval` seconds (handy for a "waiting for game..."
    GUI state) until the process appears.
    """
    names = names or PROCESS_NAMES
    log.info("Looking for process matching any of: %s", ", ".join(names))
    deadline = time.time() + timeout
    found = None
    while True:
        found = find_pid_by_names(names)
        if found or time.time() >= deadline:
            break
        time.sleep(poll_interval)

    if not found:
        log.warning("No matching process found (timeout=%s)", timeout)
        raise ProcessLookupError(
            f"None of these processes are running: {', '.join(names)}"
        )

    pid, matched_name = found
    log.info("Found process: PID=%s name=%s", pid, matched_name)
    pm = pymem.Pymem()
    pm.open_process_from_id(pid)
    log.debug("Process handle opened: %s", pm.process_handle)

    module = None
    for mod in pymem.process.enum_process_module(pm.process_handle):
        if mod.name.lower() in {n.lower() for n in MAIN_MODULE_CANDIDATES}:
            module = mod
            break
    if module is None:
        # Fall back to the first module (should be the main exe) if our
        # name list didn't match exactly.
        mods = list(pymem.process.enum_process_module(pm.process_handle))
        if not mods:
            log.error("Could not enumerate any modules for PID %s", pid)
            raise RuntimeError("Could not enumerate any modules for the target process")
        module = mods[0]
        log.warning("Main module not matched by name; falling back to first "
                     "enumerated module: %s", module.name)

    base = module.lpBaseOfDll
    size = module.SizeOfImage
    exe_path = getattr(module, "filename", None)
    log.info("Module: name=%s base=%s size=%s path=%s", module.name, hex(base), hex(size), exe_path)

    sha256 = _sha256_of_file(exe_path) if exe_path and os.path.isfile(exe_path) else None
    delta = base - REFERENCE_IMAGE_BASE
    log.info("SHA256=%s  delta_from_reference_base=%s%s", sha256,
              "+" if delta >= 0 else "-", hex(abs(delta)))

    return TargetProcess(
        pm=pm,
        pid=pid,
        process_name=matched_name,
        module_name=module.name,
        base=base,
        size=size,
        delta=delta,
        exe_path=exe_path,
        sha256=sha256,
    )


def is_game_running(names=None) -> bool:
    """Cheap, non-blocking check -- used by the GUI's background poller to
    decide whether it's time to attempt an auto-attach."""
    return find_pid_by_names(names or PROCESS_NAMES) is not None


def is_process_alive(target: TargetProcess) -> bool:
    try:
        exit_code = wintypes.DWORD()
        STILL_ACTIVE = 259
        handle = target.pm.process_handle
        if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == STILL_ACTIVE
    except Exception:
        return False
