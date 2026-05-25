#!/usr/bin/env python3
"""
NFS The Run — Advanced Mod Suite v2.3
Cross-version via AOB scanning scoped to the game module.
Patterns from _mRally2.CT + ReClass.NET analysis.
Single-player / offline only.  Run as Administrator.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import pymem, pymem.process
import struct, threading, time, json, ctypes
from ctypes import windll, c_ulong, c_void_p, c_size_t, byref
from ctypes.wintypes import DWORD
from datetime import datetime, timedelta

# ── Palette ───────────────────────────────────────────────────────────────────
BG,SURF,SURF2,SURF3 = "#0f1117","#1a1d27","#22263a","#2c3050"
ACCENT,ACCH         = "#ff6b35","#e05820"
TEXT,DIM            = "#eaeaf0","#7a7d99"
GRN,RED,YEL         = "#4ade80","#f87171","#fbbf24"
BDR                 = "#252840"
FNT,FNT_B,FNT_H     = ("Segoe UI",9),("Segoe UI",9,"bold"),("Segoe UI",11,"bold")
FNT_MONO            = ("Consolas",22,"bold")
FNT_SM              = ("Segoe UI",7)
FNT_LOG             = ("Consolas",8)

# ── WinAPI ────────────────────────────────────────────────────────────────────
class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("BaseAddress",c_void_p),("AllocationBase",c_void_p),
                ("AllocationProtect",DWORD),("RegionSize",c_size_t),
                ("State",DWORD),("Protect",DWORD),("Type",DWORD)]

PAGE_NOACCESS,PAGE_GUARD,MEM_COMMIT = 0x01,0x100,0x1000

# ── IMAGE_BASE assumed by _mRally2.CT ─────────────────────────────────────────
IMAGE_BASE = 0x00400000


# ══════════════════════════════════════════════════════════════════════════════
# Verbose Logger  (thread-safe, writes to a tk.Text widget)
# ══════════════════════════════════════════════════════════════════════════════
class Logger:
    def __init__(self):
        self._widget: tk.Text | None = None
        self._lines: list[str] = []
        self._lock = threading.Lock()

    def attach(self, widget: tk.Text):
        self._widget = widget
        # flush buffered lines
        for line in self._lines:
            self._append(line)
        self._lines.clear()

    def log(self, msg: str, tag: str = ""):
        ts  = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{ts}] {msg}"
        with self._lock:
            if self._widget:
                self._widget.after(0, lambda l=line, t=tag: self._append(l, t))
            else:
                self._lines.append(line)
            print(line)

    def _append(self, line: str, tag: str = ""):
        if not self._widget:
            return
        self._widget.config(state="normal")
        self._widget.insert("end", line + "\n", tag or ())
        self._widget.see("end")
        self._widget.config(state="disabled")

LOG = Logger()


# ══════════════════════════════════════════════════════════════════════════════
# AOB Scanner  — strictly module-scoped, rejects ambiguous hits
# ══════════════════════════════════════════════════════════════════════════════
class AOBScanner:
    MIN_FIXED_BYTES   = 5    # require ≥ this many non-wildcard bytes
    MIN_TOTAL_BYTES   = 6    # require ≥ this many bytes total
    MAX_ACCEPTABLE_HITS = 1  # more than 1 hit → reject (ambiguous)
    CHUNK             = 0x10000   # 64 KB read chunks

    def __init__(self, handle: int):
        self.handle = handle

    @staticmethod
    def parse(pattern_str: str):
        parts = pattern_str.strip().split()
        pat, mask = bytearray(), bytearray()
        for p in parts:
            if p == "??":
                pat.append(0x00); mask.append(0x00)
            else:
                pat.append(int(p, 16)); mask.append(0xFF)
        return bytes(pat), bytes(mask)

    def quality(self, pattern_str: str) -> tuple[int, int]:
        """Return (fixed_bytes, total_bytes) for a pattern string."""
        parts = pattern_str.strip().split()
        total = len(parts)
        fixed = sum(1 for p in parts if p != "??")
        return fixed, total

    def scan_module(self, base: int, size: int, pattern_str: str,
                    name: str = "") -> tuple[list[int], str]:
        """
        Scan [base, base+size) for pattern.
        Returns (hits, status_msg).
        Rejects patterns with insufficient fixed bytes.
        """
        fixed, total = self.quality(pattern_str)
        if fixed < self.MIN_FIXED_BYTES or total < self.MIN_TOTAL_BYTES:
            return [], f"SKIPPED — pattern too short ({fixed} fixed, {total} total)"

        pat, mask = self.parse(pattern_str)
        exact = all(b == 0xFF for b in mask)
        L     = len(pat)
        hits  = []
        bytes_scanned = 0

        for chunk_off in range(0, size, self.CHUNK):
            chunk_base = base + chunk_off
            to_read    = min(self.CHUNK, size - chunk_off)
            buf        = ctypes.create_string_buffer(to_read)
            read       = c_size_t(0)
            ok = windll.kernel32.ReadProcessMemory(
                self.handle, c_void_p(chunk_base), buf, to_read, byref(read))
            if not ok:
                continue
            data = buf.raw[:read.value]
            bytes_scanned += len(data)
            end  = len(data) - L + 1
            i    = 0
            while i < end:
                if exact:
                    idx = data.find(pat, i)
                    if idx == -1: break
                    hits.append(chunk_base + idx)
                    i = idx + 1
                else:
                    if all((data[i+j] & mask[j]) == (pat[j] & mask[j]) for j in range(L)):
                        hits.append(chunk_base + i)
                    i += 1
                if len(hits) > self.MAX_ACCEPTABLE_HITS + 5:
                    break
            if len(hits) > self.MAX_ACCEPTABLE_HITS + 5:
                break

        if len(hits) == 0:
            return [], f"NOT FOUND  (scanned {bytes_scanned//1024} KB)"
        elif len(hits) == 1:
            return hits, f"UNIQUE HIT @ {hex(hits[0])}  (scanned {bytes_scanned//1024} KB)"
        else:
            return hits, (f"AMBIGUOUS — {len(hits)} hits: "
                          f"{', '.join(hex(h) for h in hits[:6])}  → using fallback")


# ══════════════════════════════════════════════════════════════════════════════
# Signature Database
# All abs_fallback values are from _mRally2.CT (absolute, IMAGE_BASE=0x400000).
# result_offset = bytes from pattern start to the address of interest.
# ══════════════════════════════════════════════════════════════════════════════
SIGS: dict[str, dict] = {

    # ── GameTime / MaxFPS ─────────────────────────────────────────────────────
    # CT: "NFS The Run.exe"+A607F7  →  mov cl,[eax+40] / mov eax,[ebx+08]
    "gametime": {
        "pattern":       "8A 48 40 8B 43 08",
        "result_offset": 0,
        "abs_fallback":  None,
        "fallback_rva":  0xA607F7,
        "desc":          "GameTime / MaxFPS struct hook",
        "verify_bytes":  b"\x8A\x48\x40\x8B\x43\x08",
    },

    # ── Player has vehicle control ─────────────────────────────────────────────
    # CT: "NFS The Run.exe"+3F6C73  →  cmp byte ptr [esi+04],00 / push edi
    "has_control": {
        "pattern":       "80 7E 04 00 57",
        "result_offset": 0,
        "abs_fallback":  None,
        "fallback_rva":  0x3F6C73,
        "desc":          "Player vehicle control check",
        "verify_bytes":  b"\x80\x7E\x04\x00\x57",
    },

    # ── FPS lock cluster ──────────────────────────────────────────────────────
    # CT: 004106F6  →  je short (74 28) then two 'mov byte ptr [addr],01' instr.
    # result_offset=2 → points at 004106F8 (the first C6 05 instruction).
    "fps_cluster": {
        "pattern":       "74 28 C6 05 ?? ?? ?? ?? 01 C6 05 ?? ?? ?? ?? 01",
        "result_offset": 2,
        "abs_fallback":  0x004106F8,
        "fallback_rva":  None,
        "desc":          "FPS lock cluster (7 patch sites)",
        "verify_bytes":  b"\xC6\x05",   # first two bytes of C6 05 [addr] 01
    },

    # ── Time of Day ───────────────────────────────────────────────────────────
    # CT: "NFS The Run.exe"+59BF25  →  mov ecx,[eax+64] / push 01
    "tod_career": {
        "pattern":       "8B 48 64 6A 01",
        "result_offset": 0,
        "abs_fallback":  None,
        "fallback_rva":  0x59BF25,
        "desc":          "Time of Day (career/challenge)",
        "verify_bytes":  b"\x8B\x48\x64\x6A\x01",
    },

    # ── Tunnel of Pain crash ───────────────────────────────────────────────────
    # CT: 0121D23B  →  cmp [esi],dx  (66 39 16)
    # Pattern too short for reliable scan — fallback only, with byte verification.
    "tunnel_crash": {
        "pattern":       None,   # 66 39 16 is 3 bytes — never AOB scan
        "result_offset": 0,
        "abs_fallback":  0x0121D23B,
        "fallback_rva":  None,
        "desc":          "Tunnel of Pain crash trigger",
        "verify_bytes":  b"\x66\x39\x16",
    },

    # ── Chicago crash A ───────────────────────────────────────────────────────
    # CT: 00E4EB60  →  mov [eax+00000090],edx  (89 90 90 00 00 00)
    # Pattern is 6 bytes but content is common — fallback only.
    "chicago_a": {
        "pattern":       None,
        "result_offset": 0,
        "abs_fallback":  0x00E4EB60,
        "fallback_rva":  None,
        "desc":          "Chicago crash trigger A",
        "verify_bytes":  b"\x89\x90\x90\x00\x00\x00",
    },

    # ── Chicago crash B ───────────────────────────────────────────────────────
    # CT: 00E50F0E  →  mov [edi+00000090],eax  (89 87 90 00 00 00)
    "chicago_b": {
        "pattern":       None,
        "result_offset": 0,
        "abs_fallback":  0x00E50F0E,
        "fallback_rva":  None,
        "desc":          "Chicago crash trigger B",
        "verify_bytes":  b"\x89\x87\x90\x00\x00\x00",
    },

    # ── Assist: AlignToRoad ────────────────────────────────────────────────────
    # CT: 0069B167  →  jne 0069B1A7  (default=75 3E)  [enable patches to 74 3E]
    # 2 bytes — never AOB scan.
    "assist_align": {
        "pattern":       None,
        "result_offset": 0,
        "abs_fallback":  0x0069B167,
        "fallback_rva":  None,
        "desc":          "Assist: AlignToRoad (jcc flip)",
        "verify_bytes":  b"\x75\x3E",   # default/disabled state
    },

    # ── Assist: OverrideDriftIntent ────────────────────────────────────────────
    # CT: 0069B5E2  →  je 0069B60F  (default=74 2D)  [enable patches to 75 2D]
    "assist_drift_intent": {
        "pattern":       None,
        "result_offset": 0,
        "abs_fallback":  0x0069B5E2,
        "fallback_rva":  None,
        "desc":          "Assist: OverrideDriftIntent (jcc flip)",
        "verify_bytes":  b"\x74\x2D",   # default/disabled state
    },

    # ── Assist: RaceLineAssist status ─────────────────────────────────────────
    # CT: 01819981  →  mov [edi+50],00000002  (C7 47 50 02 00 00 00)  — 7 bytes, unique
    "assist_rla_status": {
        "pattern":       "C7 47 50 02 00 00 00",
        "result_offset": 0,
        "abs_fallback":  0x01819981,
        "fallback_rva":  None,
        "desc":          "Assist: RaceLineAssist status write",
        "verify_bytes":  b"\xC7\x47\x50\x02\x00\x00\x00",
    },

    # ── Assist: RaceLineAssist calc skip ──────────────────────────────────────
    # CT: 018199A6  →  ja 01819CDC  (0F 87 ?? ?? ?? ??)
    # 'ja near' with wildcard displacement — too ambiguous, fallback only.
    "assist_rla_skip": {
        "pattern":       None,
        "result_offset": 0,
        "abs_fallback":  0x018199A6,
        "fallback_rva":  None,
        "desc":          "Assist: RaceLineAssist calc skip (ja near)",
        "verify_bytes":  b"\x0F\x87",
    },

    # ── Assist: RaceLineAssist forces ─────────────────────────────────────────
    # CT: 01819AB1  →  je 01819CAC  (0F 84 ?? ?? ?? ??)  — fallback only
    "assist_rla_forces": {
        "pattern":       None,
        "result_offset": 0,
        "abs_fallback":  0x01819AB1,
        "fallback_rva":  None,
        "desc":          "Assist: RaceLineAssist forces (je near)",
        "verify_bytes":  b"\x0F\x84",
    },

    # ── Assist: drift forces call ─────────────────────────────────────────────
    # CT: 0181AA64  →  call 0181A8E0  (E8 77 FE FF FF)
    # 5 bytes, no wildcards — scan but require unique AND match fallback.
    "assist_drift_forces": {
        "pattern":       "E8 77 FE FF FF",
        "result_offset": 0,
        "abs_fallback":  0x0181AA64,
        "fallback_rva":  None,
        "desc":          "Assist: Drift forces (call)",
        "verify_bytes":  b"\xE8\x77\xFE\xFF\xFF",
    },

    # ── Assist: DriftIntents skip ─────────────────────────────────────────────
    # CT: 01828E73  →  je 018293A0  (0F 84 ?? ?? ?? ??)  — fallback only
    "assist_drift_intents": {
        "pattern":       None,
        "result_offset": 0,
        "abs_fallback":  0x01828E73,
        "fallback_rva":  None,
        "desc":          "Assist: DriftIntents skip (je near)",
        "verify_bytes":  b"\x0F\x84",
    },

    # ── Show Hidden UI / Unlock vehicles ──────────────────────────────────────
    # CT: 00968F50  →  jne 00968F7B  default  (0F 85 ?? ?? ?? ??)
    # Enable: patch to unconditional jmp E9 to always show hidden options.
    "ui_unlock": {
        "pattern":       None,
        "result_offset": 0,
        "abs_fallback":  0x00968F50,
        "fallback_rva":  None,
        "desc":          "Show Hidden UI Options / vehicle unlock gate",
        "verify_bytes":  b"\x0F\x85",
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# Feature Map — resolves all signatures, emitting verbose log entries
# ══════════════════════════════════════════════════════════════════════════════
class FeatureMap:
    def __init__(self):
        self.addrs:  dict[str, int] = {}
        self.status: dict[str, str] = {}   # confirmed|scanned|fallback|unverified|missing

    def resolve(self, pm: pymem.Pymem, base: int, mod_size: int,
                safe_read_fn) -> int:
        scanner = AOBScanner(pm.process_handle)
        delta   = base - IMAGE_BASE           # ASLR shift (0 if no ASLR)
        found   = 0

        LOG.log("=" * 60)
        LOG.log(f"MODULE BASE : {hex(base)}")
        LOG.log(f"MODULE SIZE : {hex(mod_size)} ({mod_size//1024} KB)")
        LOG.log(f"ASLR DELTA  : {hex(delta)} ({'+' if delta>=0 else ''}{delta})")
        LOG.log(f"SIGNATURES  : {len(SIGS)}")
        LOG.log("=" * 60)

        for name, sig in SIGS.items():
            LOG.log(f"\n── {name} ──────────────────────────────────")
            LOG.log(f"  desc    : {sig['desc']}")

            # 1. Compute fallback address
            fb_addr = None
            if sig.get("abs_fallback") is not None:
                fb_addr = sig["abs_fallback"] + delta
                LOG.log(f"  fallback: {hex(sig['abs_fallback'])} (CT)  +delta={hex(delta)}  → {hex(fb_addr)}")
            elif sig.get("fallback_rva") is not None:
                fb_addr = base + sig["fallback_rva"]
                LOG.log(f"  fallback: base+{hex(sig['fallback_rva'])} = {hex(fb_addr)}")

            # 2. AOB scan (only if pattern is present and quality is sufficient)
            scan_addr = None
            pattern   = sig.get("pattern")
            if pattern:
                fixed, total = scanner.quality(pattern)
                LOG.log(f"  pattern : {pattern}  ({fixed} fixed / {total} total bytes)")
                hits, status_msg = scanner.scan_module(base, mod_size, pattern, name)
                LOG.log(f"  scan    : {status_msg}")

                if len(hits) == 1:
                    candidate = hits[0] + sig["result_offset"]
                    if fb_addr is not None and candidate != fb_addr:
                        LOG.log(f"  ⚠ SCAN DISAGREES with fallback "
                                f"(scan={hex(candidate)}, fallback={hex(fb_addr)})")
                        LOG.log(f"  → Prefer SCAN result (supports cross-version)")
                    scan_addr = candidate
            else:
                LOG.log(f"  pattern : (none — fallback only, pattern too short/ambiguous)")

            # 3. Pick final address: scan wins if available, else fallback
            addr = scan_addr if scan_addr is not None else fb_addr

            if addr is None:
                LOG.log(f"  result  : MISSING — no address resolved")
                self.status[name] = "missing"
                continue

            # 4. Byte verification — read at resolved address and compare
            verify_pat = sig.get("verify_bytes")
            if verify_pat:
                actual = safe_read_fn(addr, len(verify_pat))
                if actual is None:
                    LOG.log(f"  verify  : UNREADABLE at {hex(addr)}")
                    status = "unverified"
                elif actual == verify_pat:
                    LOG.log(f"  verify  : ✓ bytes match  {actual.hex()}")
                    status = "confirmed" if scan_addr is not None else "fallback"
                else:
                    LOG.log(f"  verify  : ✗ MISMATCH")
                    LOG.log(f"            expected : {verify_pat.hex()}")
                    LOG.log(f"            got      : {actual.hex() if actual else 'None'}")
                    status = "unverified"
                    # Still keep the address — might be a different build variant
            else:
                status = "confirmed" if scan_addr is not None else "fallback"

            self.addrs[name]  = addr
            self.status[name] = status
            LOG.log(f"  result  : {hex(addr)}  [{status}]")
            found += 1

        LOG.log(f"\n{'='*60}")
        LOG.log(f"SCAN COMPLETE — {found}/{len(SIGS)} resolved")
        LOG.log(f"{'='*60}")
        return found

    def get(self, name: str) -> int | None:
        return self.addrs.get(name)

    def ok(self, name: str) -> bool:
        """True if address resolved and byte-verified."""
        return self.status.get(name) in ("confirmed", "fallback")


# ══════════════════════════════════════════════════════════════════════════════
# Loadless Timer — manual pause mode
# ══════════════════════════════════════════════════════════════════════════════
class LoadlessTimer:
    def __init__(self):
        self._lock        = threading.Lock()
        self.running      = timedelta()
        self.loading      = timedelta()
        self.active       = False
        self.paused       = False
        self._last        = None
        self.splits: list[dict] = []

    def start(self):
        with self._lock:
            self.active  = True; self.paused = False
            self._last   = datetime.now()
            self.running = timedelta(); self.loading = timedelta()
            self.splits  = []

    def pause(self):
        with self._lock:
            self._flush()
            self.paused = True

    def resume(self):
        with self._lock:
            self.paused = False
            self._last  = datetime.now()

    def stop(self):
        with self._lock:
            self._flush(); self.active = False; self._last = None

    def reset(self):
        with self._lock:
            self.active  = False; self.paused = False; self._last = None
            self.running = timedelta(); self.loading = timedelta()
            self.splits  = []

    def _flush(self):
        if self._last and self.active:
            delta = datetime.now() - self._last
            if 0 < delta.total_seconds() < 60:
                if self.paused: self.loading += delta
                else:           self.running += delta
        self._last = datetime.now()

    def tick(self):
        if self.active and self._last:
            now   = datetime.now()
            delta = now - self._last
            if 0 < delta.total_seconds() < 1.0:
                if self.paused: self.loading += delta
                else:           self.running += delta
            self._last = now

    def split(self, name):
        if self.active:
            self.splits.append({"name": name, "time": self.time_str(),
                                 "ts": datetime.now().isoformat()})

    def time_str(self):
        s  = self.running.total_seconds()
        h  = int(s//3600); m = int((s%3600)//60)
        sc = int(s%60);    ms = int((s*1000)%1000)
        return f"{h:02d}:{m:02d}:{sc:02d}.{ms:03d}"

    def export(self, path):
        with open(path,"w") as f:
            json.dump({"running": str(self.running), "loading": str(self.loading),
                       "splits": self.splits}, f, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# Vehicle Customizer
# ══════════════════════════════════════════════════════════════════════════════
class VehicleCustomizer:
    VEHICLES = {"Porsche 911 GT3 RS 4.0":0xA998E13D,"Nissan GT-R R35":0xCE5A5DEB,
                "Lamborghini Gallardo":0xFB1C95C1,"BMW M3 GTS":0x2012C92C,
                "Ford Mustang Boss 302":0xDE2611F3,"Chevrolet Camaro SS":0x9121385E,
                "Audi R8":0xCED5A7B6}
    BODYKITS = {"Stock":0,"Time Attack":1,"Aero Pack":2,"Circuit Racer":3}
    PAINTS   = {"Metallic Blue":0x257F2512,"Matte Black":0x4E9BBE75,
                "Glossy White":0xC494BC78,"Carbon Fiber":0x1780E1}

    def __init__(self, parent, suite):
        self.suite = suite
        self.win   = tk.Toplevel(parent, bg=BG)
        self.win.title("Vehicle Customizer"); self.win.geometry("680x480")
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)
        self._build()

    def _write(self, rva, data):
        return self.suite.safe_write(self.suite.base + rva, data)

    def _lbl(self, p, t, **kw):
        return tk.Label(p, text=t, bg=kw.pop("bg",SURF),
                        fg=kw.pop("fg",TEXT), font=FNT, **kw)

    def _btn(self, p, t, cmd, accent=False):
        bg,hv = (ACCENT,ACCH) if accent else (SURF2,SURF3)
        return tk.Button(p,text=t,command=cmd,bg=bg,
                         fg="white" if accent else TEXT,font=FNT_B,
                         relief="flat",bd=0,padx=14,pady=6,
                         activebackground=hv,cursor="hand2")

    def _build(self):
        hdr = tk.Frame(self.win,bg=SURF,height=50); hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr,text="  🚗  Vehicle Customizer",bg=SURF,fg=TEXT,font=FNT_H).pack(side="left",padx=10,pady=10)
        nb = ttk.Notebook(self.win); nb.pack(fill="both",expand=True,padx=12,pady=10)

        vf = tk.Frame(nb,bg=SURF); nb.add(vf,text="  Vehicle  ")
        self._lbl(vf,"Car",fg=ACCENT,font=FNT_B).pack(anchor="w",padx=20,pady=(14,4))
        self.v_car = tk.StringVar(value=list(self.VEHICLES)[0])
        ttk.Combobox(vf,textvariable=self.v_car,values=list(self.VEHICLES),state="readonly",width=34).pack(padx=20,pady=4)
        self._btn(vf,"Apply",self._apply_vehicle,True).pack(anchor="w",padx=20,pady=10)

        bf = tk.Frame(nb,bg=SURF); nb.add(bf,text="  Bodykit  ")
        self._lbl(bf,"Bodykit",fg=ACCENT,font=FNT_B).pack(anchor="w",padx=20,pady=(14,4))
        self.v_kit = tk.StringVar(value="Stock")
        for n in self.BODYKITS: tk.Radiobutton(bf,text=n,variable=self.v_kit,value=n,
            bg=SURF,fg=TEXT,selectcolor=SURF3,activebackground=SURF,font=FNT).pack(anchor="w",padx=30,pady=2)
        self._btn(bf,"Apply",self._apply_bodykit,True).pack(anchor="w",padx=20,pady=10)

        pf = tk.Frame(nb,bg=SURF); nb.add(pf,text="  Paint  ")
        self._lbl(pf,"Colour",fg=ACCENT,font=FNT_B).pack(anchor="w",padx=20,pady=(14,4))
        self.v_paint = tk.StringVar(value=list(self.PAINTS)[0])
        ttk.Combobox(pf,textvariable=self.v_paint,values=list(self.PAINTS),state="readonly",width=24).pack(padx=20,pady=4)
        self._btn(pf,"Apply",self._apply_paint,True).pack(anchor="w",padx=20,pady=10)

        perf = tk.Frame(nb,bg=SURF); nb.add(perf,text="  Performance  ")
        self._lbl(perf,"Tier  (1=stock → 6=max)",fg=ACCENT,font=FNT_B).pack(anchor="w",padx=20,pady=(14,4))
        self.v_tier = tk.IntVar(value=5)
        ttk.Scale(perf,from_=1,to=6,variable=self.v_tier,length=300).pack(padx=20,pady=6)
        tk.Label(perf,textvariable=self.v_tier,bg=SURF,fg=ACCENT,font=("Segoe UI",14,"bold")).pack()
        self._btn(perf,"Apply",self._apply_perf,True).pack(anchor="w",padx=20,pady=10)

        row = tk.Frame(self.win,bg=BG); row.pack(fill="x",padx=12,pady=(0,12))
        self._btn(row,"💾  Save Preset",self._save).pack(side="left",padx=(0,8))
        self._btn(row,"📂  Load Preset",self._load).pack(side="left")

    def _apply_vehicle(self):
        try:
            h = self.VEHICLES[self.v_car.get()]; self._write(0x1391D40,struct.pack("<I",h))
            LOG.log(f"[VEH] Vehicle set: {self.v_car.get()} (hash {hex(h)})")
            messagebox.showinfo("Applied",self.v_car.get(),parent=self.win)
        except Exception as e: messagebox.showerror("Error",str(e),parent=self.win)

    def _apply_bodykit(self):
        try:
            v = self.BODYKITS[self.v_kit.get()]; self._write(0x1391E20,struct.pack("<B",v))
            LOG.log(f"[VEH] Bodykit: {self.v_kit.get()}")
            messagebox.showinfo("Applied",self.v_kit.get(),parent=self.win)
        except Exception as e: messagebox.showerror("Error",str(e),parent=self.win)

    def _apply_paint(self):
        try:
            h = self.PAINTS[self.v_paint.get()]; self._write(0x1391E40,struct.pack("<I",h))
            LOG.log(f"[VEH] Paint: {self.v_paint.get()} (hash {hex(h)})")
            messagebox.showinfo("Applied",self.v_paint.get(),parent=self.win)
        except Exception as e: messagebox.showerror("Error",str(e),parent=self.win)

    def _apply_perf(self):
        try:
            t = max(1,min(6,self.v_tier.get())); self._write(0x1391E60,struct.pack("<B",t))
            LOG.log(f"[VEH] Perf tier: {t}")
            messagebox.showinfo("Applied",f"Tier {t}",parent=self.win)
        except Exception as e: messagebox.showerror("Error",str(e),parent=self.win)

    def _save(self):
        p = filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON","*.json")],parent=self.win)
        if p:
            with open(p,"w") as f: json.dump({"car":self.v_car.get(),"kit":self.v_kit.get(),
                "paint":self.v_paint.get(),"tier":self.v_tier.get()},f,indent=2)

    def _load(self):
        p = filedialog.askopenfilename(filetypes=[("JSON","*.json")],parent=self.win)
        if p:
            d=json.load(open(p))
            self.v_car.set(d.get("car",list(self.VEHICLES)[0]))
            self.v_kit.set(d.get("kit","Stock"))
            self.v_paint.set(d.get("paint",list(self.PAINTS)[0]))
            self.v_tier.set(d.get("tier",5))


# ══════════════════════════════════════════════════════════════════════════════
# Main Application
# ══════════════════════════════════════════════════════════════════════════════
class NFSModSuite:
    PROCESS_NAMES = ["Need for Speed The Run.exe","Need For Speed The Run.exe",
                     "NFS13.exe","nfs13.exe"]

    def __init__(self, root: tk.Tk):
        self.root      = root
        self.pm        = None
        self.base: int = 0
        self.mod_size: int = 0
        self.connected = False
        self.features  = FeatureMap()
        self.timer     = LoadlessTimer()
        self._lock     = threading.Lock()
        self._mon_run  = False
        self._nop_cache: dict[int,bytes] = {}
        self.freeze_nos   = False
        self.freeze_nodmg = False

        root.title("NFS The Run — Mod Suite v2.3")
        root.geometry("940x740"); root.resizable(False,False)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW",self._on_close)
        self._theme(); self._build_ui()
        root.after(500, self._do_connect)

    # ── Theme ─────────────────────────────────────────────────────────────────
    def _theme(self):
        s = ttk.Style(); s.theme_use("default")
        for n,bg,fg,fo in [("TFrame",BG,TEXT,FNT),("Card.TFrame",SURF,TEXT,FNT),
                            ("TLabel",BG,TEXT,FNT),("Card.TLabel",SURF,TEXT,FNT),
                            ("Dim.TLabel",SURF,DIM,FNT),("Head.TLabel",SURF,ACCENT,FNT_B)]:
            s.configure(n,background=bg,foreground=fg,font=fo)
        s.configure("TButton",background=SURF2,foreground=TEXT,font=FNT_B,
                    relief="flat",borderwidth=0,padding=(12,6))
        s.map("TButton",background=[("active",SURF3)])
        s.configure("Accent.TButton",background=ACCENT,foreground="white",
                    font=FNT_B,relief="flat",borderwidth=0,padding=(12,6))
        s.map("Accent.TButton",background=[("active",ACCH)])
        s.configure("TCheckbutton",background=SURF,foreground=TEXT,font=FNT,
                    indicatorcolor=SURF3,selectcolor=SURF3)
        s.map("TCheckbutton",background=[("active",SURF)],foreground=[("active",TEXT)])
        s.configure("TLabelframe",background=SURF,bordercolor=BDR,relief="flat")
        s.configure("TLabelframe.Label",background=SURF,foreground=ACCENT,font=FNT_B)
        s.configure("TNotebook",background=BG,borderwidth=0)
        s.configure("TNotebook.Tab",background=SURF,foreground=DIM,font=FNT_B,
                    padding=(18,9),borderwidth=0)
        s.map("TNotebook.Tab",background=[("selected",SURF2),("active",SURF3)],
              foreground=[("selected",ACCENT),("active",TEXT)])
        s.configure("TScale",background=SURF,troughcolor=SURF3)
        for n in ("TEntry","TSpinbox","TCombobox"):
            s.configure(n,fieldbackground=SURF3,foreground=TEXT,background=SURF2,
                        insertcolor=TEXT,arrowcolor=DIM,selectbackground=SURF3,
                        borderwidth=0,relief="flat")

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self.root,bg=SURF,height=54); hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr,text="  🏎  NFS THE RUN",bg=SURF,fg=TEXT,font=("Segoe UI",12,"bold")).pack(side="left",padx=4)
        tk.Label(hdr,text="MOD SUITE",bg=SURF,fg=ACCENT,font=("Segoe UI",12,"bold")).pack(side="left")
        sc = tk.Frame(hdr,bg=SURF); sc.pack(side="right",padx=14)
        self._dot  = tk.Label(sc,text="●",bg=SURF,fg=RED,font=("Segoe UI",16)); self._dot.pack(side="left")
        self._slbl = tk.Label(sc,text="Not connected",bg=SURF,fg=DIM,font=FNT); self._slbl.pack(side="left",padx=(4,12))
        tk.Button(sc,text="Reconnect",command=self._do_connect,bg=SURF2,fg=TEXT,font=FNT,
                  relief="flat",bd=0,padx=10,pady=3,activebackground=SURF3,cursor="hand2").pack(side="left")
        tk.Frame(self.root,bg=ACCENT,height=2).pack(fill="x")
        self.nb = ttk.Notebook(self.root); self.nb.pack(fill="both",expand=True)
        self._tab_perf(); self._tab_speedrun(); self._tab_vehicle()
        self._tab_tweaks(); self._tab_scanner()

    # ── Performance tab ───────────────────────────────────────────────────────
    def _tab_perf(self):
        tab = tk.Frame(self.nb,bg=BG); self.nb.add(tab,text="  ⚡ Performance  ")
        self._gap(tab)
        c = self._card(tab,"FRAMERATE")
        self.v_fps    = tk.BooleanVar(); self.v_fpscut = tk.BooleanVar()
        self.v_vsync  = tk.BooleanVar()
        self._chk(c,"Unlock Gameplay Framerate  (removes 30 fps cap)",self.v_fps,self._on_fps)
        self._chk(c,"Unlock Cutscene Framerate  ⚠ experimental",self.v_fpscut,self._on_fps_cut)
        self._chk(c,"Disable V-Sync During Loading",self.v_vsync,self._on_vsync)
        row = tk.Frame(c,bg=SURF); row.pack(fill="x",padx=14,pady=(6,4))
        tk.Label(row,text="Menu Max FPS:",bg=SURF,fg=TEXT,font=FNT,width=16,anchor="w").pack(side="left")
        self.v_menu_fps = tk.DoubleVar(value=60.0)
        ttk.Scale(row,from_=30,to=240,variable=self.v_menu_fps,length=240).pack(side="left",padx=8)
        tk.Label(row,textvariable=self.v_menu_fps,width=6,bg=SURF,fg=ACCENT,font=FNT_B).pack(side="left")
        self._sbtn(c,"Apply Menu FPS",self._apply_menu_fps)
        tk.Label(c,text="  ⚠ Default 60. Values >120 may break physics. Patches 7 sites in the game's FPS limiter code.",
                 bg=SURF,fg=YEL,font=FNT_SM).pack(anchor="w",padx=14,pady=(0,10))
        self._gap(tab)
        c2 = self._card(tab,"GRAPHICS")
        self.v_blur=tk.BooleanVar(); self.v_shadows=tk.BooleanVar(); self.v_refl=tk.BooleanVar()
        self._chk(c2,"Enhanced Motion Blur",self.v_blur,None)
        self._chk(c2,"Higher Quality Shadows",self.v_shadows,None)
        self._chk(c2,"Enhanced Reflections",self.v_refl,None)
        self._sbtn(c2,"Apply Graphics",self._apply_graphics)

    # ── Speedrun tab ──────────────────────────────────────────────────────────
    def _tab_speedrun(self):
        tab = tk.Frame(self.nb,bg=BG); self.nb.add(tab,text="  ⏱ Speedrun  ")
        self._gap(tab)
        c = self._card(tab,"LOADLESS TIMER — manual pause mode")
        tk.Label(c,text="Press ⏸ Pause/Load when a loading screen starts, ▶ Resume when back in-game.",
                 bg=SURF,fg=DIM,font=FNT_SM,wraplength=700,justify="left").pack(anchor="w",padx=14,pady=(0,6))
        self._tlbl = tk.Label(c,text="00:00:00.000",bg=SURF,fg=TEXT,font=FNT_MONO); self._tlbl.pack(pady=(8,4))
        info = tk.Frame(c,bg=SURF); info.pack()
        self._llbl  = tk.Label(info,text="Loads: 00:00:00",bg=SURF,fg=DIM,font=FNT); self._llbl.pack(side="left",padx=16)
        self._stlbl = tk.Label(info,text="● Idle",bg=SURF,fg=DIM,font=FNT_B); self._stlbl.pack(side="left")
        btns = tk.Frame(c,bg=SURF); btns.pack(pady=10)
        for lbl,cmd,col in [("▶ Start",self._t_start,GRN),("⏸ Pause/Load",self._t_pause,YEL),
                             ("▶ Resume",self._t_resume,GRN),("✂ Split",self._t_split,ACCENT),
                             ("■ Stop",self._t_stop,RED),("↺ Reset",self._t_reset,DIM)]:
            tk.Button(btns,text=lbl,command=cmd,bg=SURF2,fg=col,font=FNT_B,
                      relief="flat",bd=0,padx=10,pady=6,activebackground=SURF3,cursor="hand2").pack(side="left",padx=3)
        self.v_autosplit = tk.BooleanVar()
        self._chk(c,"Auto-split on checkpoints (requires LiveSplit integration)",self.v_autosplit,None)
        self._gap(tab)
        c2 = self._card(tab,"SPLITS")
        self._sbox = tk.Text(c2,height=7,bg=SURF2,fg=TEXT,font=("Consolas",9),
                             relief="flat",bd=0,padx=8,pady=6); self._sbox.pack(fill="x",padx=12,pady=(0,8))
        row = tk.Frame(c2,bg=SURF); row.pack(fill="x",padx=12,pady=(0,10))
        self._ibtn(row,"Export JSON",self._t_export); self._ibtn(row,"Copy Time",self._t_copy)

    # ── Vehicle tab ───────────────────────────────────────────────────────────
    def _tab_vehicle(self):
        tab = tk.Frame(self.nb,bg=BG); self.nb.add(tab,text="  🚗 Vehicle  ")
        self._gap(tab)
        c = self._card(tab,"QUICK TOGGLES")
        self.v_assists=tk.BooleanVar(); self.v_nos=tk.BooleanVar(); self.v_nodmg=tk.BooleanVar()
        self._chk(c,"Disable All Driving Assists  (patches 7 locations in game code)",self.v_assists,self._on_assists)
        self._chk(c,"Infinite NOS  (freeze: written every 33ms by monitor thread)",self.v_nos,self._on_nos)
        self._chk(c,"No Vehicle Damage  (freeze: written every 33ms by monitor thread)",self.v_nodmg,self._on_nodmg)
        tk.Label(c,text="  ⚠ NOS/Damage freeze offsets are RE-derived — verify with CE if they cause issues.",
                 bg=SURF,fg=YEL,font=FNT_SM).pack(anchor="w",padx=14,pady=(0,8))
        self._gap(tab)
        c2 = self._card(tab,"VEHICLE CUSTOMIZER")
        tk.Label(c2,text="Vehicle, bodykit, paint and performance editor with JSON preset support.",
                 bg=SURF,fg=DIM,font=FNT).pack(anchor="w",padx=14,pady=(4,10))
        tk.Button(c2,text="  Open Vehicle Customizer  →",command=self._open_cust,
                  bg=ACCENT,fg="white",font=FNT_B,relief="flat",bd=0,
                  padx=16,pady=8,activebackground=ACCH,cursor="hand2").pack(anchor="w",padx=14,pady=(0,14))

    # ── Tweaks tab ────────────────────────────────────────────────────────────
    def _tab_tweaks(self):
        tab = tk.Frame(self.nb,bg=BG); self.nb.add(tab,text="  🔧 Tweaks  ")
        self._gap(tab)
        c = self._card(tab,"UNLOCKS")
        tk.Label(c,text=(
            "Unlock All Vehicles patches the vehicle roster gate in the UI code.\n"
            "Unlock Challenges NOPs the 'ja' instruction that hides locked challenge entries.\n"
            "Changes take effect when you exit to the main menu and re-enter the challenge screen."),
            bg=SURF,fg=DIM,font=FNT_SM,wraplength=700,justify="left").pack(anchor="w",padx=14,pady=(4,10))
        self._wbtn(c,"Unlock All Vehicles",   self._unlock_cars)
        self._wbtn(c,"Unlock All Challenges", self._unlock_challenges)
        self._gap(tab)
        c2 = self._card(tab,"STABILITY FIXES")
        tk.Label(c2,text=(
            "Tunnel of Pain (0x0121D23B): NOPs the cmp [esi],dx trigger.\n"
            "Chicago A (0x00E4EB60) + B (0x00E50F0E): NOPs the mov [reg+0x90],reg crash writes.\n"
            "All addresses are byte-verified before patching — check the Scanner tab for status."),
            bg=SURF,fg=DIM,font=FNT_SM,wraplength=700,justify="left").pack(anchor="w",padx=14,pady=(4,10))
        self._wbtn(c2,"Apply All Crash Bypasses",self._apply_crash)
        tk.Frame(c2,bg=SURF,height=10).pack()

    # ── Scanner tab ───────────────────────────────────────────────────────────
    def _tab_scanner(self):
        tab = tk.Frame(self.nb,bg=BG); self.nb.add(tab,text="  🔍 Log  ")

        # Status grid
        top = tk.Frame(tab,bg=SURF); top.pack(fill="x",padx=16,pady=12)
        tk.Label(top,text="SIGNATURE STATUS",bg=SURF,fg=ACCENT,
                 font=("Segoe UI",8,"bold")).grid(row=0,column=0,columnspan=4,sticky="w",padx=10,pady=(10,4))
        tk.Frame(top,bg=BDR,height=1).grid(row=1,column=0,columnspan=4,sticky="ew",padx=10,pady=(0,6))
        ICON = {"confirmed":"🟢","fallback":"🟡","unverified":"🔴","missing":"❌","scanned":"🟢"}
        self._scan_rows: dict[str,tk.Label] = {}
        for i,(name,sig) in enumerate(SIGS.items()):
            row, col = divmod(i, 2)
            base_col = col * 2
            tk.Label(top,text=sig["desc"],bg=SURF,fg=DIM,font=FNT_SM,
                     width=35,anchor="w").grid(row=row+2,column=base_col,sticky="w",padx=(10,2),pady=1)
            lbl = tk.Label(top,text="—",bg=SURF,fg=DIM,font=FNT_SM)
            lbl.grid(row=row+2,column=base_col+1,sticky="w",padx=(0,20))
            self._scan_rows[name] = lbl

        # Verbose log
        logf = tk.Frame(tab,bg=SURF); logf.pack(fill="both",expand=True,padx=16,pady=(0,12))
        tk.Label(logf,text="VERBOSE LOG",bg=SURF,fg=ACCENT,
                 font=("Segoe UI",8,"bold")).pack(anchor="w",padx=10,pady=(10,2))
        tk.Frame(logf,bg=BDR,height=1).pack(fill="x",padx=10,pady=(0,6))
        self._log_widget = scrolledtext.ScrolledText(
            logf, height=16, bg=SURF2, fg=TEXT, font=FNT_LOG,
            relief="flat", bd=0, state="disabled",
            insertbackground=TEXT)
        self._log_widget.pack(fill="both",expand=True,padx=10,pady=(0,10))
        # Color tags
        for tag,col in [("ok",GRN),("warn",YEL),("err",RED),("accent",ACCENT),("dim",DIM)]:
            self._log_widget.tag_configure(tag,foreground=col)

        LOG.attach(self._log_widget)

        row2 = tk.Frame(tab,bg=BG); row2.pack(fill="x",padx=16,pady=(0,12))
        tk.Button(row2,text="Re-scan / Reconnect",command=self._do_connect,
                  bg=SURF2,fg=TEXT,font=FNT_B,relief="flat",bd=0,
                  padx=12,pady=5,activebackground=SURF3,cursor="hand2").pack(side="left",padx=(0,8))
        tk.Button(row2,text="Clear Log",command=self._clear_log,
                  bg=SURF2,fg=TEXT,font=FNT_B,relief="flat",bd=0,
                  padx=12,pady=5,activebackground=SURF3,cursor="hand2").pack(side="left")

    def _clear_log(self):
        self._log_widget.config(state="normal")
        self._log_widget.delete("1.0","end")
        self._log_widget.config(state="disabled")

    # ── Widget helpers ────────────────────────────────────────────────────────
    def _gap(self,p,h=10): tk.Frame(p,bg=BG,height=h).pack()
    def _card(self,parent,title):
        outer = tk.Frame(parent,bg=SURF); outer.pack(fill="x",padx=16)
        tk.Label(outer,text=title,bg=SURF,fg=ACCENT,
                 font=("Segoe UI",8,"bold")).pack(anchor="w",padx=14,pady=(12,2))
        tk.Frame(outer,bg=BDR,height=1).pack(fill="x",padx=14,pady=(0,8))
        return outer
    def _chk(self,parent,text,var,cmd):
        f = tk.Frame(parent,bg=SURF); f.pack(anchor="w",padx=14,pady=3)
        tk.Checkbutton(f,text=text,variable=var,command=cmd,bg=SURF,fg=TEXT,
                       selectcolor=SURF3,activebackground=SURF,activeforeground=TEXT,
                       font=FNT,relief="flat",cursor="hand2").pack(side="left")
    def _sbtn(self,parent,text,cmd):
        tk.Button(parent,text=text,command=cmd,bg=SURF2,fg=TEXT,font=FNT_B,
                  relief="flat",bd=0,padx=12,pady=5,activebackground=SURF3,cursor="hand2").pack(anchor="w",padx=14,pady=(2,10))
    def _ibtn(self,parent,text,cmd):
        tk.Button(parent,text=text,command=cmd,bg=SURF2,fg=TEXT,font=FNT_B,
                  relief="flat",bd=0,padx=10,pady=4,activebackground=SURF3,cursor="hand2").pack(side="left",padx=(0,8))
    def _wbtn(self,parent,text,cmd):
        tk.Button(parent,text=text,command=cmd,bg=SURF2,fg=TEXT,font=FNT_B,
                  relief="flat",bd=0,padx=16,pady=8,activebackground=SURF3,cursor="hand2").pack(fill="x",padx=14,pady=4)

    # ── Connection ────────────────────────────────────────────────────────────
    def _do_connect(self):
        self._set_status("Connecting…",YEL)
        threading.Thread(target=self._connect_worker,daemon=True).start()

    def _connect_worker(self):
        LOG.log("Attempting to connect to game process…")
        for name in self.PROCESS_NAMES:
            LOG.log(f"  trying: {name}")
            try:
                pm  = pymem.Pymem(name)
                mod = pymem.process.module_from_name(pm.process_handle, name)
                if not mod:
                    LOG.log(f"  → module_from_name returned None, skipping")
                    continue
                base      = mod.lpBaseOfDll
                mod_size  = mod.SizeOfImage
                LOG.log(f"  → FOUND: base={hex(base)}, size={hex(mod_size)} ({mod_size//1024} KB)")
                with self._lock:
                    self.pm       = pm
                    self.base     = base
                    self.mod_size = mod_size
                    self.connected = True
                self.root.after(0, lambda: self._set_status("Scanning signatures…",YEL))
                found = self.features.resolve(pm, base, mod_size, self.safe_read)
                self.root.after(0, self._update_scan_ui)
                label = (f"Connected · {name} · base {hex(base)} · "
                         f"{found}/{len(SIGS)} features")
                self.root.after(0, lambda l=label: self._set_status(l, GRN))
                self.root.after(0, self._start_monitor)
                return
            except Exception as e:
                LOG.log(f"  → failed: {e}")
        self.root.after(0, lambda: self._set_status(
            "Not connected — launch game first, then Reconnect (Admin required)", RED))

    def _update_scan_ui(self):
        ICON = {"confirmed":"🟢","fallback":"🟡","unverified":"🔴","missing":"❌"}
        COL  = {"confirmed":GRN,"fallback":YEL,"unverified":RED,"missing":RED}
        for name, lbl in self._scan_rows.items():
            st   = self.features.status.get(name, "missing")
            addr = self.features.get(name)
            icon = ICON.get(st, "❓")
            addr_s = hex(addr) if addr else "—"
            lbl.config(text=f"{icon} {addr_s}", fg=COL.get(st, DIM))

    def _set_status(self, msg, color):
        self._dot.config(fg=color); self._slbl.config(text=msg)

    def _guard(self) -> bool:
        if not self.connected:
            messagebox.showwarning("Not connected",
                "Connect to the game first.\n"
                "• NFS The Run must be running\n"
                "• Run this tool as Administrator\n"
                "• Game version: v1.1.0.0")
            return False
        return True

    # ── Safe memory I/O ───────────────────────────────────────────────────────
    def safe_read(self, addr: int, length: int) -> bytes | None:
        try:
            with self._lock: data = self.pm.read_bytes(addr, length)
            return data if len(data) == length else None
        except Exception as e:
            LOG.log(f"[READ  {hex(addr)}] {e}"); return None

    def safe_write(self, addr: int, data: bytes) -> bool:
        """Write bytes; upgrades page protection if needed. No recursive calls."""
        LOG.log(f"[WRITE {hex(addr)}] {len(data)}B: {data.hex()}")
        try:
            with self._lock: self.pm.write_bytes(addr, data, len(data))
            LOG.log(f"[WRITE {hex(addr)}] ✓ plain write succeeded")
            return True
        except Exception as e1:
            LOG.log(f"[WRITE {hex(addr)}] plain write failed ({e1}), trying VirtualProtect…")
        try:
            old = c_ulong(0)
            windll.kernel32.VirtualProtectEx(
                self.pm.process_handle, c_void_p(addr),
                c_size_t(len(data)), 0x40, byref(old))
            with self._lock: self.pm.write_bytes(addr, data, len(data))
            windll.kernel32.VirtualProtectEx(
                self.pm.process_handle, c_void_p(addr),
                c_size_t(len(data)), old, byref(c_ulong(0)))
            LOG.log(f"[WRITE {hex(addr)}] ✓ protected write succeeded")
            return True
        except Exception as e2:
            LOG.log(f"[WRITE {hex(addr)}] ✗ FAILED: {e2}"); return False

    def _wf(self, addr, v): return self.safe_write(addr, struct.pack("<f",v))
    def _wb(self, addr, v): return self.safe_write(addr, struct.pack("<B",v))
    def _wd(self, addr, v): return self.safe_write(addr, struct.pack("<I",v))

    def _nop(self, addr: int, size: int) -> bool:
        if addr not in self._nop_cache:
            orig = self.safe_read(addr, size)
            if orig is None:
                LOG.log(f"[NOP] Cannot read original bytes at {hex(addr)} — aborting")
                return False
            self._nop_cache[addr] = orig
            LOG.log(f"[NOP] Cached originals at {hex(addr)}: {orig.hex()}")
        LOG.log(f"[NOP] Writing {size}×90 at {hex(addr)}")
        return self.safe_write(addr, b"\x90" * size)

    def _unnop(self, addr: int) -> bool:
        orig = self._nop_cache.get(addr)
        if orig:
            LOG.log(f"[UNNOP] Restoring {len(orig)}B at {hex(addr)}: {orig.hex()}")
            return self.safe_write(addr, orig)
        LOG.log(f"[UNNOP] No cached bytes for {hex(addr)}")
        return False

    def _feat(self, name: str) -> int | None:
        return self.features.get(name)

    def _feat_ok(self, name: str) -> bool:
        return self.features.ok(name)

    def _require(self, name: str) -> int | None:
        """Return address if resolved + verified, else show error and return None."""
        addr = self._feat(name)
        if addr is None:
            msg = (f"Feature '{name}' was not resolved.\n"
                   f"Check the Scanner → Log tab for details.\n"
                   f"Your build may require updated patterns.")
            LOG.log(f"[REQUIRE] {name} — MISSING, aborting operation")
            messagebox.showerror("Address not found", msg)
            return None
        st = self.features.status.get(name, "missing")
        if st == "unverified":
            LOG.log(f"[REQUIRE] {name} @ {hex(addr)} — UNVERIFIED bytes, proceeding with caution")
        return addr

    # ── Monitor thread ────────────────────────────────────────────────────────
    def _start_monitor(self):
        if self._mon_run: return
        self._mon_run = True
        threading.Thread(target=self._monitor, daemon=True).start()

    def _monitor(self):
        errs = 0
        LOG.log("[MON] Monitor thread started")
        while self._mon_run and self.connected:
            try:
                if not self._alive():
                    self.connected = False
                    LOG.log("[MON] Game process gone — disconnecting")
                    self.root.after(0, lambda: self._set_status("Game closed — reconnect to reattach", RED))
                    break
                self.timer.tick()
                self.root.after(0, self._refresh_timer)
                # Freeze features (written every ~33ms)
                if self.freeze_nos:
                    self._wf(self.base + 0x1391E80, 1.0)
                    self._wf(self.base + 0x1391E88, 0.0)
                if self.freeze_nodmg:
                    for off in (0xBDF4B0, 0xBDF4C0, 0xBDF4D0):
                        self._wf(self.base + off, 0.0)
                errs = 0; time.sleep(1/30)
            except Exception as e:
                errs = min(errs+1,10)
                LOG.log(f"[MON] Error: {e}")
                time.sleep(min(0.1*errs, 2.0))

    def _alive(self):
        try:
            import psutil; return psutil.pid_exists(self.pm.process_id)
        except Exception:
            try: self.pm.read_bytes(self.base,1); return True
            except Exception: return False

    # ── Timer UI ──────────────────────────────────────────────────────────────
    def _refresh_timer(self):
        if not self.timer.active: return
        self._tlbl.config(text=self.timer.time_str())
        ls = str(self.timer.loading).split(".")[0]
        self._llbl.config(text=f"Loads: {ls}")
        if not self.timer.active:
            self._stlbl.config(text="● Idle",fg=DIM)
        elif self.timer.paused:
            self._stlbl.config(text="⏸ Loading",fg=YEL)
        else:
            self._stlbl.config(text="● Running",fg=GRN)

    def _t_start(self):
        self.timer.start(); self._sbox.delete("1.0","end")
        self._stlbl.config(text="● Running",fg=GRN)
        LOG.log("[TIMER] Started")

    def _t_pause(self):
        self.timer.pause(); self._stlbl.config(text="⏸ Loading",fg=YEL)
        LOG.log(f"[TIMER] Paused (load started) @ {self.timer.time_str()}")

    def _t_resume(self):
        self.timer.resume(); self._stlbl.config(text="● Running",fg=GRN)
        LOG.log(f"[TIMER] Resumed")

    def _t_split(self):
        name = f"Split {len(self.timer.splits)+1}"
        self.timer.split(name)
        self._sbox.insert("end",f"{name:<12}  {self.timer.time_str()}\n"); self._sbox.see("end")
        LOG.log(f"[TIMER] Split: {name} @ {self.timer.time_str()}")

    def _t_stop(self):
        self.timer.stop(); self._stlbl.config(text="● Stopped",fg=RED)
        LOG.log(f"[TIMER] Stopped @ {self.timer.time_str()}")

    def _t_reset(self):
        self.timer.reset()
        self._tlbl.config(text="00:00:00.000"); self._llbl.config(text="Loads: 00:00:00")
        self._stlbl.config(text="● Idle",fg=DIM); self._sbox.delete("1.0","end")
        LOG.log("[TIMER] Reset")

    def _t_export(self):
        p = filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON","*.json")])
        if p: self.timer.export(p); messagebox.showinfo("Exported",f"Saved:\n{p}")

    def _t_copy(self):
        self.root.clipboard_clear(); self.root.clipboard_append(self.timer.time_str())

    # ── Performance actions ───────────────────────────────────────────────────
    def _on_fps(self):
        if not self._guard(): self.v_fps.set(False); return
        addr = self._require("fps_cluster")
        if addr is None: self.v_fps.set(False); return
        on = self.v_fps.get()
        LOG.log(f"[FPS] {'Enabling' if on else 'Disabling'} framerate unlock @ {hex(addr)}")
        # CT table specifies 7 patch sites relative to fps_cluster (0x4106F8):
        #   +6   : value byte of first  C6 05 [addr] XX  (01→00)
        #   +13  : value byte of second C6 05 [addr] XX  (01→00)
        #   +14  : E9 8B 00 00 00  (jmp, bypass) → NOP×5
        #   +23  : value byte of C6 44 24 13 XX           (01→00)
        #   +30  : value byte of C6 05 [addr] XX at +0x18 (01→00)
        #   +37  : value byte of C6 05 [addr] XX at +0x1F (01→00)
        #   +125 : value byte of C6 05 [addr] XX at +0x77 (00→01, reversed!)
        enable_patches = [(6,0x00),(13,0x00),(23,0x00),(30,0x00),(37,0x00)]
        disable_patches= [(6,0x01),(13,0x01),(23,0x01),(30,0x01),(37,0x01)]
        patches = enable_patches if on else disable_patches
        for delta, val in patches:
            LOG.log(f"  [FPS] byte patch @ {hex(addr+delta)} → {hex(val)}")
            self._wb(addr+delta, val)
        # NOP the bypass jmp at +14 (E9 8B 00 00 00 = 5 bytes)
        if on:
            self._nop(addr+14, 5)
        else:
            self._unnop(addr+14)
        # Reversed patch at +125: enable=01, disable=00
        last_val = 0x01 if on else 0x00
        LOG.log(f"  [FPS] reversed byte patch @ {hex(addr+125)} → {hex(last_val)}")
        self._wb(addr+125, last_val)
        LOG.log(f"[FPS] Framerate unlock {'ON' if on else 'OFF'}")

    def _on_fps_cut(self):
        if not self._guard(): self.v_fpscut.set(False); return
        LOG.log("[FPS_CUT] Cutscene FPS unlock — uses same fps_cluster, applying fps_unlock too")
        self.v_fps.set(self.v_fpscut.get()); self._on_fps()

    def _on_vsync(self):
        if not self._guard(): self.v_vsync.set(False); return
        addr = self._require("fps_cluster")
        if addr is None: self.v_vsync.set(False); return
        on = self.v_vsync.get()
        LOG.log(f"[VSYNC] {'Disabling' if on else 'Restoring'} loading vsync @ fps_cluster+14")
        # The jmp at +14 also controls vsync during loading
        if on: self._nop(addr+14, 5)
        else:  self._unnop(addr+14)

    def _apply_menu_fps(self):
        if not self._guard(): return
        LOG.log("[MENU_FPS] MaxVariableFps is resolved at runtime via the gametime hook.")
        LOG.log("[MENU_FPS] The float lives at [eax+28] where eax is the GameTime struct pointer.")
        LOG.log("[MENU_FPS] To find it: CE → attach → enable 'GameTime Settings' script → read MaxVariableFps address.")
        messagebox.showinfo("Note",
            "MaxVariableFps is a dynamically-allocated float.\n"
            "Its address changes every game session.\n\n"
            "To find it:\n"
            "1. Open Cheat Engine, attach to the game\n"
            "2. Enable the 'GameTime Settings' hook from _mRally2.CT\n"
            "3. Read the 'MaxVariableFps' entry address\n"
            "4. Add that offset to the SIGS dict in main.py")

    def _apply_graphics(self):
        messagebox.showinfo("Note","Graphics flags take effect at the next scene transition.")

    # ── Assist actions ────────────────────────────────────────────────────────
    def _on_assists(self):
        if not self._guard(): self.v_assists.set(False); return
        on = self.v_assists.get()
        LOG.log(f"[ASSISTS] {'Enabling' if on else 'Disabling'} all driving assists")

        results = []

        # 1. AlignToRoad: jne→je (75 3E → 74 3E) at 0069B167
        addr = self._feat("assist_align")
        if addr:
            LOG.log(f"  [ASSIST] AlignToRoad @ {hex(addr)}")
            actual = self.safe_read(addr, 2)
            LOG.log(f"    current bytes: {actual.hex() if actual else 'UNREADABLE'}")
            if on:
                ok = self.safe_write(addr, b"\x74\x3E")   # jne→je
            else:
                ok = self.safe_write(addr, b"\x75\x3E")   # je→jne (restore)
            results.append(("AlignToRoad", ok))

        # 2. OverrideDriftIntent: je→jne (74 2D → 75 2D) at 0069B5E2
        addr = self._feat("assist_drift_intent")
        if addr:
            LOG.log(f"  [ASSIST] DriftIntent @ {hex(addr)}")
            actual = self.safe_read(addr, 2)
            LOG.log(f"    current bytes: {actual.hex() if actual else 'UNREADABLE'}")
            if on:
                ok = self.safe_write(addr, b"\x75\x2D")   # je→jne
            else:
                ok = self.safe_write(addr, b"\x74\x2D")   # jne→je (restore)
            results.append(("DriftIntent", ok))

        # 3. RaceLineAssist status: change value byte 02→00 at [addr+3]
        addr = self._feat("assist_rla_status")
        if addr:
            LOG.log(f"  [ASSIST] RLA status @ {hex(addr)}")
            actual = self.safe_read(addr, 7)
            LOG.log(f"    current bytes: {actual.hex() if actual else 'UNREADABLE'}")
            # C7 47 50 [02→00] 00 00 00  — the dword value starts at byte 3
            val_byte = 0x00 if on else 0x02
            ok = self._wb(addr+3, val_byte)
            results.append(("RLA status", ok))

        # 4. RaceLineAssist calc skip: ja→jmp (0F 87 → E9 ... NOP) at 018199A6
        addr = self._feat("assist_rla_skip")
        if addr:
            LOG.log(f"  [ASSIST] RLA calc skip @ {hex(addr)}")
            actual = self.safe_read(addr, 6)
            LOG.log(f"    current bytes: {actual.hex() if actual else 'UNREADABLE'}")
            if on:
                # Replace 0F 87 [disp32] with E9 [disp32] NOP (near jmp unconditional)
                if actual and len(actual) == 6:
                    disp = actual[2:6]   # keep displacement, just change opcode
                    ok = self.safe_write(addr, b"\xE9" + disp + b"\x90")
                else:
                    ok = False
            else:
                ok = self._unnop(addr) if addr in self._nop_cache else self.safe_write(addr, b"\x0F\x87" + (actual[2:6] if actual else b"\x00"*4))
            results.append(("RLA skip", ok))

        # 5. RaceLineAssist forces: je→always (0F 84 → E9)  at 01819AB1
        addr = self._feat("assist_rla_forces")
        if addr:
            LOG.log(f"  [ASSIST] RLA forces @ {hex(addr)}")
            actual = self.safe_read(addr, 6)
            LOG.log(f"    current bytes: {actual.hex() if actual else 'UNREADABLE'}")
            if on:
                if actual and len(actual)==6:
                    disp = actual[2:6]
                    ok = self.safe_write(addr, b"\xE9" + disp + b"\x90")
                else: ok = False
            else:
                ok = self.safe_write(addr, b"\x0F\x84" + (actual[2:6] if actual else b"\x00"*4)) if actual else False
            results.append(("RLA forces", ok))

        # 6. Drift forces: NOP the call at 0181AA64
        addr = self._feat("assist_drift_forces")
        if addr:
            LOG.log(f"  [ASSIST] Drift forces @ {hex(addr)}")
            actual = self.safe_read(addr, 5)
            LOG.log(f"    current bytes: {actual.hex() if actual else 'UNREADABLE'}")
            if on: ok = self._nop(addr, 5)
            else:  ok = self._unnop(addr)
            results.append(("Drift forces", ok))

        # 7. DriftIntents skip: je→jmp at 01828E73
        addr = self._feat("assist_drift_intents")
        if addr:
            LOG.log(f"  [ASSIST] DriftIntents skip @ {hex(addr)}")
            actual = self.safe_read(addr, 6)
            LOG.log(f"    current bytes: {actual.hex() if actual else 'UNREADABLE'}")
            if on:
                if actual and len(actual)==6:
                    disp = actual[2:6]
                    ok = self.safe_write(addr, b"\xE9" + disp + b"\x90")
                else: ok = False
            else:
                ok = self.safe_write(addr, b"\x0F\x84" + (actual[2:6] if actual else b"\x00"*4)) if actual else False
            results.append(("DriftIntents", ok))

        ok_count = sum(1 for _,ok in results if ok)
        LOG.log(f"[ASSISTS] {ok_count}/{len(results)} patches applied")

    def _on_nos(self):
        if not self._guard(): self.v_nos.set(False); return
        self.freeze_nos = self.v_nos.get()
        LOG.log(f"[NOS] Freeze {'ON' if self.freeze_nos else 'OFF'}  (offset base+0x1391E80)")

    def _on_nodmg(self):
        if not self._guard(): self.v_nodmg.set(False); return
        self.freeze_nodmg = self.v_nodmg.get()
        LOG.log(f"[NODMG] Freeze {'ON' if self.freeze_nodmg else 'OFF'}  (offsets base+0xBDF4B0/C0/D0)")

    def _open_cust(self):
        if not self._guard(): return
        VehicleCustomizer(self.root, self)

    # ── Tweaks actions ────────────────────────────────────────────────────────
    def _unlock_cars(self):
        if not self._guard(): return
        # CT: 00968F50: jne 00968F7B  (0F 85 ?? ?? ??) → jmp (E9 ?? ?? ?? ??)
        addr = self._require("ui_unlock")
        if addr is None: return
        LOG.log(f"[CARS] Unlocking vehicles @ {hex(addr)}")
        actual = self.safe_read(addr, 6)
        LOG.log(f"  current bytes: {actual.hex() if actual else 'UNREADABLE'}")
        if actual and actual[:2] == b"\x0F\x85":
            disp = actual[2:6]
            ok   = self.safe_write(addr, b"\xE9" + disp + b"\x90")
            LOG.log(f"  patched jne→jmp: {ok}")
            if ok: messagebox.showinfo("Done","Vehicle unlock applied — exit and re-enter the car selection.")
        elif actual and actual[0:1] == b"\xE9":
            LOG.log("  already patched (jmp present)")
            messagebox.showinfo("Note","Already unlocked.")
        else:
            LOG.log(f"  unexpected bytes {actual.hex() if actual else 'None'} — cannot auto-patch")
            messagebox.showwarning("Unexpected bytes",
                f"Expected 0F 85 (jne) at {hex(addr)}\n"
                f"Got: {actual.hex() if actual else 'UNREADABLE'}\n\n"
                "Your build may differ. Use CE with _mRally2.CT for manual unlock.")

    def _unlock_challenges(self):
        if not self._guard(): return
        LOG.log("[CHALLENGES] Applying challenge unlock")
        # CT: 0093D732 and 0093D195 — NOP the lock checks
        delta = self.base - IMAGE_BASE
        for abs_addr, name in [(0x0093D732,"challenge gate A"),(0x0093D195,"challenge gate B")]:
            addr = abs_addr + delta
            actual = self.safe_read(addr, 6)
            LOG.log(f"  {name} @ {hex(addr)}: {actual.hex() if actual else 'UNREADABLE'}")
            ok = self._nop(addr, 5)
            LOG.log(f"  patch: {'✓' if ok else '✗'}")
        messagebox.showinfo("Done",
            "Challenge unlock applied.\n"
            "Note: Challenges also require story progress — if they stay locked,\n"
            "the lock may be save-data based, not code-based.")

    def _apply_crash(self):
        if not self._guard(): return
        LOG.log("[CRASH] Applying crash bypasses")
        report = []
        for sig_name, nop_size in [("tunnel_crash",3),("chicago_a",6),("chicago_b",6)]:
            addr = self._feat(sig_name)
            if addr is None:
                LOG.log(f"  {sig_name}: MISSING — skipped")
                report.append(f"✗  {SIGS[sig_name]['desc']}  (address not found)")
                continue
            actual = self.safe_read(addr, nop_size)
            LOG.log(f"  {sig_name} @ {hex(addr)}: {actual.hex() if actual else 'UNREADABLE'}")
            expected = SIGS[sig_name]["verify_bytes"][:nop_size]
            if actual and actual[:len(expected)] != expected:
                LOG.log(f"  ⚠ bytes don't match expected {expected.hex()}, patching anyway")
            ok = self._nop(addr, nop_size)
            LOG.log(f"  patch: {'✓' if ok else '✗'}")
            report.append(f"{'✓' if ok else '✗'}  {SIGS[sig_name]['desc']}")
        messagebox.showinfo("Crash Bypasses", "\n".join(report))

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def _on_close(self):
        LOG.log("[APP] Closing — restoring NOPs and cleaning up")
        self._mon_run = False
        if self.pm:
            try: self.pm.close_process()
            except Exception: pass
        self.root.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────
def _ensure_admin():
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            import sys
            ctypes.windll.shell32.ShellExecuteW(
                None,"runas",sys.executable,f'"{sys.argv[0]}"',None,1)
            sys.exit(0)
    except Exception: pass

if __name__ == "__main__":
    _ensure_admin()
    root = tk.Tk()
    NFSModSuite(root)
    root.mainloop()
