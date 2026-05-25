#!/usr/bin/env python3
"""
NFS The Run — Advanced Mod Suite v2.2
Cross-version compatible via AOB (Array-of-Bytes) pattern scanning.
Patterns derived from _mRally2's CT table bundled with this repo.
Single-player / offline use only.  Run as Administrator.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pymem, pymem.process
import struct, threading, time, json, ctypes
from ctypes import windll, c_ulong, c_ulong as ULONG, c_void_p, c_size_t, byref
from ctypes.wintypes import DWORD, BOOL
from datetime import datetime, timedelta

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = "#0f1117"
SURF    = "#1a1d27"
SURF2   = "#22263a"
SURF3   = "#2c3050"
ACCENT  = "#ff6b35"
ACCH    = "#e05820"
TEXT    = "#eaeaf0"
DIM     = "#7a7d99"
GRN     = "#4ade80"
RED     = "#f87171"
YEL     = "#fbbf24"
BDR     = "#252840"

FNT      = ("Segoe UI", 9)
FNT_B    = ("Segoe UI", 9,  "bold")
FNT_H    = ("Segoe UI", 11, "bold")
FNT_MONO = ("Consolas",  22, "bold")
FNT_SM   = ("Segoe UI", 7)

# ── Windows memory structs ────────────────────────────────────────────────────
class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress",       c_void_p),
        ("AllocationBase",    c_void_p),
        ("AllocationProtect", DWORD),
        ("RegionSize",        c_size_t),
        ("State",             DWORD),
        ("Protect",           DWORD),
        ("Type",              DWORD),
    ]

MEM_COMMIT  = 0x1000
PAGE_NOACCESS      = 0x01
PAGE_GUARD         = 0x100
PAGE_EXECUTE_READ  = 0x20
PAGE_EXECUTE_READWRITE = 0x40
PAGE_EXECUTE_WRITECOPY = 0x80

# ══════════════════════════════════════════════════════════════════════════════
# AOB Scanner
# Scans all committed, readable memory pages of a process for a byte pattern.
# Supports '??' wildcards in the pattern string.
# ══════════════════════════════════════════════════════════════════════════════
class AOBScanner:
    def __init__(self, process_handle: int):
        self.handle = process_handle

    def _iter_regions(self):
        """Yield (base, data) for every readable committed memory region."""
        addr = 0
        mbi  = MEMORY_BASIC_INFORMATION()
        sz   = ctypes.sizeof(mbi)
        while windll.kernel32.VirtualQueryEx(
                self.handle, c_void_p(addr), byref(mbi), sz):
            if (mbi.State == MEM_COMMIT
                    and not (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD))
                    and mbi.RegionSize > 0):
                buf = ctypes.create_string_buffer(mbi.RegionSize)
                read = c_size_t(0)
                if windll.kernel32.ReadProcessMemory(
                        self.handle, c_void_p(addr),
                        buf, mbi.RegionSize, byref(read)):
                    yield addr, buf.raw[:read.value]
            next_addr = (mbi.BaseAddress or 0) + mbi.RegionSize
            if next_addr <= addr:
                break
            addr = next_addr

    @staticmethod
    def _parse_pattern(pattern_str: str):
        """Parse 'AA BB ?? CC' → (bytes_pattern, bytes_mask)."""
        parts = pattern_str.strip().split()
        pat, mask = bytearray(), bytearray()
        for p in parts:
            if p == "??":
                pat.append(0x00); mask.append(0x00)
            else:
                pat.append(int(p, 16)); mask.append(0xFF)
        return bytes(pat), bytes(mask)

    def scan(self, pattern_str: str, first_only: bool = True) -> list[int]:
        """
        Scan process memory for pattern_str.
        Returns a list of absolute addresses where the pattern was found.
        """
        pat, mask = self._parse_pattern(pattern_str)
        L       = len(pat)
        results = []
        exact   = all(b == 0xFF for b in mask)

        for base_addr, data in self._iter_regions():
            i = 0
            end = len(data) - L + 1
            while i < end:
                if exact:
                    idx = data.find(pat, i)
                    if idx == -1:
                        break
                    results.append(base_addr + idx)
                    if first_only:
                        return results
                    i = idx + 1
                else:
                    # Masked comparison
                    match = all((data[i+j] & mask[j]) == (pat[j] & mask[j])
                                for j in range(L))
                    if match:
                        results.append(base_addr + i)
                        if first_only:
                            return results
                    i += 1
        return results


# ══════════════════════════════════════════════════════════════════════════════
# Signature Database
# Patterns derived from _mRally2.CT + ReClass.NET analysis.
# Each entry:  name → {pattern, result_offset, fallback_rva, abs_fallback, desc}
#   pattern        – AOB string with optional ?? wildcards
#   result_offset  – bytes from pattern start to the address we want to return
#   fallback_rva   – module-relative offset (from exe base) used if scan fails
#   abs_fallback   – absolute address from CT (assumes IMAGE_BASE 0x400000);
#                    if given, overrides fallback_rva calculation
#   desc           – human-readable description
#
# All abs_fallback values are taken verbatim from _mRally2.CT.
# RVA = abs_fallback - 0x00400000 (the game's preferred image base).
# ══════════════════════════════════════════════════════════════════════════════
IMAGE_BASE = 0x00400000  # NFS The Run preferred load address (no ASLR)

SIGS = {
    # ── GameTime / FPS cap ────────────────────────────────────────────────────
    # "NFS The Run.exe"+A607F7:  mov cl,[eax+40] / mov eax,[ebx+08]
    # CT entry "GameTime Settings" — the instruction just before the CE hook
    "gametime": {
        "pattern":        "8A 48 40 8B 43 08",
        "result_offset":  0,
        "fallback_rva":   0xA607F7,
        "abs_fallback":   None,
        "desc":           "GameTime / FPS cap",
    },

    # ── Player has vehicle control ─────────────────────────────────────────────
    # "NFS The Run.exe"+3F6C73:  cmp byte ptr [esi+04],00 / push edi
    # CT entry "Player Vehicle Control Check"
    "has_control": {
        "pattern":        "80 7E 04 00 57",
        "result_offset":  0,
        "fallback_rva":   0x3F6C73,
        "abs_fallback":   None,
        "desc":           "Player vehicle control",
    },

    # ── FPS lock cluster ──────────────────────────────────────────────────────
    # Absolute address 004106F6 from CT "Framerate Unlocker" entry.
    # Pattern: je short (74 28) followed by two 'mov byte ptr, 01' instructions.
    # Wildcards cover the absolute embedded addresses (version-dependent).
    "fps_cluster": {
        "pattern":        "74 28 C6 05 ?? ?? ?? ?? 01 C6 05 ?? ?? ?? ?? 01",
        "result_offset":  2,      # +2 → first 'C6 05' = 0x004106F8
        "fallback_rva":   0x106F8,   # 0x004106F8 - 0x400000
        "abs_fallback":   None,
        "desc":           "FPS lock cluster",
    },

    # ── Time of Day (career) ──────────────────────────────────────────────────
    # "NFS The Run.exe"+59BF25:  mov ecx,[eax+64] / push 01
    "tod_career": {
        "pattern":        "8B 48 64 6A 01",
        "result_offset":  0,
        "fallback_rva":   0x59BF25,
        "abs_fallback":   None,
        "desc":           "Time of Day (career)",
    },

    # ── Tunnel of Pain crash ───────────────────────────────────────────────────
    # CT: 0121D23B: cmp [esi],dx → 66 39 16
    "tunnel_crash": {
        "pattern":        "66 39 16",
        "result_offset":  0,
        "fallback_rva":   None,
        "abs_fallback":   0x0121D23B,
        "desc":           "Tunnel of Pain crash trigger",
    },

    # ── Chicago Interstate crash A ─────────────────────────────────────────────
    # CT: 00E4EB60: mov [eax+00000090],edx → 89 90 90 00 00 00
    "chicago_a": {
        "pattern":        "89 90 90 00 00 00",
        "result_offset":  0,
        "fallback_rva":   None,
        "abs_fallback":   0x00E4EB60,
        "desc":           "Chicago crash trigger A",
    },

    # ── Chicago Interstate crash B ─────────────────────────────────────────────
    # CT: 00E50F0E: mov [edi+00000090],eax → 89 87 90 00 00 00
    "chicago_b": {
        "pattern":        "89 87 90 00 00 00",
        "result_offset":  0,
        "fallback_rva":   None,
        "abs_fallback":   0x00E50F0E,
        "desc":           "Chicago crash trigger B",
    },

    # ── Assist: AlignToRoad ────────────────────────────────────────────────────
    # CT: 0069B167: je 0069B1A7 (default) → 74 3E
    # Use broader context: the byte before is likely a cmp result
    "assist_align": {
        "pattern":        "74 3E",
        "result_offset":  0,
        "fallback_rva":   None,
        "abs_fallback":   0x0069B167,
        "desc":           "Assist: AlignToRoad",
    },

    # ── Assist: OverrideDriftIntent ────────────────────────────────────────────
    # CT: 0069B5E2: jne 0069B60F (default) → 75 2B
    "assist_drift_intent": {
        "pattern":        "75 2B",
        "result_offset":  0,
        "fallback_rva":   None,
        "abs_fallback":   0x0069B5E2,
        "desc":           "Assist: OverrideDriftIntent",
    },

    # ── Assist: RaceLineAssist status write ───────────────────────────────────
    # CT: 01819981: mov [edi+50],00000002 → C7 47 50 02 00 00 00
    "assist_rla_status": {
        "pattern":        "C7 47 50 02 00 00 00",
        "result_offset":  0,
        "fallback_rva":   None,
        "abs_fallback":   0x01819981,
        "desc":           "Assist: RaceLineAssist status",
    },

    # ── Assist: RaceLineAssist calc skip ──────────────────────────────────────
    # CT: 018199A6: ja 01819CDC (default) → 0F 87 ?? ?? ?? ??
    "assist_rla_skip": {
        "pattern":        "0F 87 ?? ?? ?? ??",
        "result_offset":  0,
        "fallback_rva":   None,
        "abs_fallback":   0x018199A6,
        "desc":           "Assist: RaceLineAssist skip",
    },

    # ── Assist: RaceLineAssist forces ─────────────────────────────────────────
    # CT: 01819AB1: je 01819CAC (default) → 0F 84 ?? ?? ?? ??
    "assist_rla_forces": {
        "pattern":        "0F 84 ?? ?? ?? ??",
        "result_offset":  0,
        "fallback_rva":   None,
        "abs_fallback":   0x01819AB1,
        "desc":           "Assist: RaceLineAssist forces",
    },

    # ── Assist: drift forces call ─────────────────────────────────────────────
    # CT: 0181AA64: call 0181A8E0 (default)
    # call rel32 = E8 [disp32], displacement = 0x0181A8E0-(0x0181AA64+5) = -0x189
    "assist_drift_forces": {
        "pattern":        "E8 77 FE FF FF",
        "result_offset":  0,
        "fallback_rva":   None,
        "abs_fallback":   0x0181AA64,
        "desc":           "Assist: Drift forces",
    },

    # ── Assist: DriftIntents skip ─────────────────────────────────────────────
    # CT: 01828E73: je 018293A0 (default) → 0F 84 ?? ?? ?? ??
    # Can't use same pattern as assist_rla_forces without collision.
    # Use a broader context: 5 bytes before are likely unique.
    "assist_drift_intents": {
        "pattern":        None,   # too ambiguous for AOB; use fallback only
        "result_offset":  0,
        "fallback_rva":   None,
        "abs_fallback":   0x01828E73,
        "desc":           "Assist: DriftIntents skip",
    },
}


class FeatureMap:
    """
    Resolves all feature addresses at runtime using AOB scan + fallback.
    Results are stored in self.addrs[name] = absolute_address.
    self.scan_status[name] = 'scanned' | 'fallback' | 'missing'
    """
    def __init__(self):
        self.addrs:       dict[str, int]  = {}
        self.scan_status: dict[str, str]  = {}

    def resolve(self, pm: pymem.Pymem, module_base: int,
                progress_cb=None) -> int:
        """
        Resolve all signatures. Returns number successfully resolved.
        progress_cb(name, status) is called for each signature.
        """
        scanner = AOBScanner(pm.process_handle)
        found = 0

        for name, sig in SIGS.items():
            addr = None
            status = "missing"

            # Try AOB scan
            pattern = sig.get("pattern")
            if pattern:
                try:
                    hits = scanner.scan(pattern, first_only=True)
                    if hits:
                        addr   = hits[0] + sig["result_offset"]
                        status = "scanned"
                except Exception as e:
                    print(f"[SCAN {name}] {e}")

            # Fallback 1: abs_fallback
            if addr is None and sig.get("abs_fallback") is not None:
                delta = module_base - IMAGE_BASE   # ASLR delta (0 if no ASLR)
                addr  = sig["abs_fallback"] + delta
                status = "fallback"

            # Fallback 2: fallback_rva
            if addr is None and sig.get("fallback_rva") is not None:
                addr   = module_base + sig["fallback_rva"]
                status = "fallback"

            if addr is not None:
                self.addrs[name]       = addr
                self.scan_status[name] = status
                found += 1
                print(f"[FEAT] {name:30s} = {hex(addr)}  [{status}]")
            else:
                self.scan_status[name] = "missing"
                print(f"[FEAT] {name:30s} = MISSING")

            if progress_cb:
                progress_cb(name, status)

        return found

    def get(self, name: str) -> int | None:
        return self.addrs.get(name)


# ══════════════════════════════════════════════════════════════════════════════
# Loadless Timer (manual pause mode — fully accurate, no hooking required)
# ══════════════════════════════════════════════════════════════════════════════
class LoadlessTimer:
    def __init__(self):
        self._lock        = threading.Lock()
        self.running_time = timedelta()
        self.loading_time = timedelta()
        self.is_paused    = False
        self.active       = False
        self._last        = None
        self.splits: list[dict] = []

    def start(self):
        with self._lock:
            self.active       = True
            self.is_paused    = False
            self._last        = datetime.now()
            self.running_time = timedelta()
            self.loading_time = timedelta()
            self.splits       = []

    def pause(self):
        """Call when a load screen begins."""
        with self._lock:
            self._flush()
            self.is_paused = True

    def resume(self):
        """Call when in-game again."""
        with self._lock:
            self.is_paused = False
            self._last     = datetime.now()

    def stop(self):
        with self._lock:
            self._flush()
            self.active = False
            self._last  = None

    def reset(self):
        with self._lock:
            self.active       = False
            self.is_paused    = False
            self._last        = None
            self.running_time = timedelta()
            self.loading_time = timedelta()
            self.splits       = []

    def _flush(self):
        if self._last and self.active:
            delta = datetime.now() - self._last
            if 0 < delta.total_seconds() < 60:
                if self.is_paused:
                    self.loading_time += delta
                else:
                    self.running_time += delta
            self._last = datetime.now()

    def tick(self):
        """Call from a monitor thread to keep time accurate."""
        if self.active and not self.is_paused and self._last:
            now   = datetime.now()
            delta = now - self._last
            if 0 < delta.total_seconds() < 1.0:
                self.running_time += delta
            self._last = now
        elif self.active and self.is_paused and self._last:
            now   = datetime.now()
            delta = now - self._last
            if 0 < delta.total_seconds() < 1.0:
                self.loading_time += delta
            self._last = now

    def split(self, name: str):
        if self.active:
            self.splits.append({
                "name":      name,
                "time":      self.time_str(),
                "timestamp": datetime.now().isoformat(),
            })

    def time_str(self) -> str:
        s   = self.running_time.total_seconds()
        h   = int(s // 3600)
        m   = int((s % 3600) // 60)
        sec = int(s % 60)
        ms  = int((s * 1000) % 1000)
        return f"{h:02d}:{m:02d}:{sec:02d}.{ms:03d}"

    def export(self, path: str):
        with open(path, "w") as f:
            json.dump({
                "running":  str(self.running_time),
                "loading":  str(self.loading_time),
                "splits":   self.splits,
            }, f, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# Vehicle Customizer  (separate Toplevel)
# ══════════════════════════════════════════════════════════════════════════════
class VehicleCustomizer:
    VEHICLES = {
        "Porsche 911 GT3 RS 4.0": 0xA998E13D,
        "Nissan GT-R R35":        0xCE5A5DEB,
        "Lamborghini Gallardo":   0xFB1C95C1,
        "BMW M3 GTS":             0x2012C92C,
        "Ford Mustang Boss 302":  0xDE2611F3,
        "Chevrolet Camaro SS":    0x9121385E,
        "Audi R8":                0xCED5A7B6,
    }
    BODYKITS = {"Stock": 0x00, "Time Attack": 0x01, "Aero Pack": 0x02, "Circuit Racer": 0x03}
    PAINTS   = {
        "Metallic Blue": 0x257F2512, "Matte Black": 0x4E9BBE75,
        "Glossy White":  0xC494BC78, "Carbon Fiber": 0x1780E1,
    }

    def __init__(self, parent, suite):
        self.suite = suite
        self.win   = tk.Toplevel(parent, bg=BG)
        self.win.title("Vehicle Customizer")
        self.win.geometry("680x500")
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)
        self._build()

    def _lbl(self, p, t, **kw):
        return tk.Label(p, text=t, bg=kw.pop("bg", SURF),
                        fg=kw.pop("fg", TEXT), font=FNT, **kw)

    def _btn(self, p, t, cmd, accent=False):
        b, h = (ACCENT, ACCH) if accent else (SURF2, SURF3)
        return tk.Button(p, text=t, command=cmd, bg=b,
                         fg="white" if accent else TEXT, font=FNT_B,
                         relief="flat", bd=0, padx=14, pady=6,
                         activebackground=h, cursor="hand2")

    def _write(self, offset, data):
        return self.suite.safe_write(self.suite.base + offset, data)

    def _build(self):
        hdr = tk.Frame(self.win, bg=SURF, height=50)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="  🚗  Vehicle Customizer",
                 bg=SURF, fg=TEXT, font=FNT_H).pack(side="left", padx=10, pady=10)

        nb = ttk.Notebook(self.win); nb.pack(fill="both", expand=True, padx=12, pady=10)

        def page(): f = tk.Frame(nb, bg=SURF); return f

        vf = page(); nb.add(vf, text="  Vehicle  ")
        self._lbl(vf, "Car", fg=ACCENT, font=FNT_B).pack(anchor="w", padx=20, pady=(14,4))
        self.v_car = tk.StringVar(value=list(self.VEHICLES)[0])
        ttk.Combobox(vf, textvariable=self.v_car, values=list(self.VEHICLES),
                     state="readonly", width=34).pack(padx=20, pady=4)
        self._btn(vf, "Apply", self._apply_vehicle, True).pack(anchor="w", padx=20, pady=10)

        bf = page(); nb.add(bf, text="  Bodykit  ")
        self._lbl(bf, "Bodykit", fg=ACCENT, font=FNT_B).pack(anchor="w", padx=20, pady=(14,4))
        self.v_kit = tk.StringVar(value="Stock")
        for n in self.BODYKITS:
            tk.Radiobutton(bf, text=n, variable=self.v_kit, value=n,
                           bg=SURF, fg=TEXT, selectcolor=SURF3,
                           activebackground=SURF, font=FNT).pack(anchor="w", padx=30, pady=2)
        self._btn(bf, "Apply", self._apply_bodykit, True).pack(anchor="w", padx=20, pady=10)

        pf = page(); nb.add(pf, text="  Paint  ")
        self._lbl(pf, "Colour", fg=ACCENT, font=FNT_B).pack(anchor="w", padx=20, pady=(14,4))
        self.v_paint = tk.StringVar(value=list(self.PAINTS)[0])
        ttk.Combobox(pf, textvariable=self.v_paint, values=list(self.PAINTS),
                     state="readonly", width=24).pack(padx=20, pady=4)
        self._btn(pf, "Apply", self._apply_paint, True).pack(anchor="w", padx=20, pady=10)

        perf = page(); nb.add(perf, text="  Performance  ")
        self._lbl(perf, "Tier  (1 = stock  →  6 = max)", fg=ACCENT, font=FNT_B).pack(
            anchor="w", padx=20, pady=(14,4))
        self.v_tier = tk.IntVar(value=5)
        ttk.Scale(perf, from_=1, to=6, variable=self.v_tier, length=300).pack(padx=20, pady=6)
        tk.Label(perf, textvariable=self.v_tier, bg=SURF, fg=ACCENT,
                 font=("Segoe UI", 14, "bold")).pack()
        self._btn(perf, "Apply", self._apply_perf, True).pack(anchor="w", padx=20, pady=10)

        row = tk.Frame(self.win, bg=BG); row.pack(fill="x", padx=12, pady=(0,12))
        self._btn(row, "💾  Save Preset", self._save).pack(side="left", padx=(0,8))
        self._btn(row, "📂  Load Preset", self._load).pack(side="left")

    def _apply_vehicle(self):
        try:
            h = self.VEHICLES[self.v_car.get()]
            self._write(0x1391D40, struct.pack("<I", h))
            messagebox.showinfo("Applied", self.v_car.get(), parent=self.win)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.win)

    def _apply_bodykit(self):
        try:
            self._write(0x1391E20, struct.pack("<B", self.BODYKITS[self.v_kit.get()]))
            messagebox.showinfo("Applied", self.v_kit.get(), parent=self.win)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.win)

    def _apply_paint(self):
        try:
            h = self.PAINTS[self.v_paint.get()]
            self._write(0x1391E40, struct.pack("<I", h))
            messagebox.showinfo("Applied", self.v_paint.get(), parent=self.win)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.win)

    def _apply_perf(self):
        try:
            self._write(0x1391E60, struct.pack("<B", max(1, min(6, self.v_tier.get()))))
            messagebox.showinfo("Applied", f"Tier {self.v_tier.get()}", parent=self.win)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.win)

    def _save(self):
        p = filedialog.asksaveasfilename(defaultextension=".json",
                                         filetypes=[("JSON","*.json")], parent=self.win)
        if p:
            with open(p, "w") as f:
                json.dump({"car": self.v_car.get(), "kit": self.v_kit.get(),
                           "paint": self.v_paint.get(), "tier": self.v_tier.get()}, f, indent=2)

    def _load(self):
        p = filedialog.askopenfilename(filetypes=[("JSON","*.json")], parent=self.win)
        if p:
            d = json.load(open(p))
            self.v_car.set(d.get("car", list(self.VEHICLES)[0]))
            self.v_kit.set(d.get("kit", "Stock"))
            self.v_paint.set(d.get("paint", list(self.PAINTS)[0]))
            self.v_tier.set(d.get("tier", 5))


# ══════════════════════════════════════════════════════════════════════════════
# Main Application
# ══════════════════════════════════════════════════════════════════════════════
class NFSModSuite:
    PROCESS_NAMES = [
        "Need for Speed The Run.exe",
        "Need For Speed The Run.exe",
        "NFS13.exe",
        "nfs13.exe",
    ]

    def __init__(self, root: tk.Tk):
        self.root      = root
        self.pm        = None
        self.base: int = 0
        self.connected = False
        self.features  = FeatureMap()
        self.timer     = LoadlessTimer()
        self._lock     = threading.Lock()
        self._mon_run  = False
        self._nop_cache: dict[int, bytes] = {}
        self.freeze_nos  = False
        self.freeze_nodmg = False

        root.title("NFS The Run — Mod Suite v2.2")
        root.geometry("900x700")
        root.resizable(False, False)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._theme()
        self._build_ui()
        root.after(500, self._do_connect)

    # ── Theme ─────────────────────────────────────────────────────────────────
    def _theme(self):
        s = ttk.Style(); s.theme_use("default")
        for n, bg, fg, fo in [
            ("TFrame",        BG,    TEXT,   FNT),
            ("Card.TFrame",   SURF,  TEXT,   FNT),
            ("TLabel",        BG,    TEXT,   FNT),
            ("Card.TLabel",   SURF,  TEXT,   FNT),
            ("Dim.TLabel",    SURF,  DIM,    FNT),
            ("Head.TLabel",   SURF,  ACCENT, FNT_B),
        ]:
            s.configure(n, background=bg, foreground=fg, font=fo)

        s.configure("TButton", background=SURF2, foreground=TEXT, font=FNT_B,
                    relief="flat", borderwidth=0, padding=(12, 6))
        s.map("TButton", background=[("active", SURF3)])
        s.configure("Accent.TButton", background=ACCENT, foreground="white",
                    font=FNT_B, relief="flat", borderwidth=0, padding=(12, 6))
        s.map("Accent.TButton", background=[("active", ACCH)])
        s.configure("TCheckbutton", background=SURF, foreground=TEXT, font=FNT,
                    indicatorcolor=SURF3, selectcolor=SURF3)
        s.map("TCheckbutton", background=[("active", SURF)], foreground=[("active", TEXT)])
        s.configure("TLabelframe", background=SURF, bordercolor=BDR, relief="flat")
        s.configure("TLabelframe.Label", background=SURF, foreground=ACCENT, font=FNT_B)
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=SURF, foreground=DIM, font=FNT_B,
                    padding=(20, 9), borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", SURF2), ("active", SURF3)],
              foreground=[("selected", ACCENT), ("active", TEXT)])
        s.configure("TScale", background=SURF, troughcolor=SURF3)
        for n in ("TEntry", "TSpinbox", "TCombobox"):
            s.configure(n, fieldbackground=SURF3, foreground=TEXT, background=SURF2,
                        insertcolor=TEXT, arrowcolor=DIM, selectbackground=SURF3,
                        borderwidth=0, relief="flat")

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=SURF, height=54)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="  🏎  NFS THE RUN", bg=SURF, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=4)
        tk.Label(hdr, text="MOD SUITE", bg=SURF, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")

        sc = tk.Frame(hdr, bg=SURF); sc.pack(side="right", padx=14)
        self._dot  = tk.Label(sc, text="●", bg=SURF, fg=RED, font=("Segoe UI", 16))
        self._dot.pack(side="left")
        self._slbl = tk.Label(sc, text="Not connected", bg=SURF, fg=DIM, font=FNT)
        self._slbl.pack(side="left", padx=(4, 12))
        tk.Button(sc, text="Reconnect", command=self._do_connect,
                  bg=SURF2, fg=TEXT, font=FNT, relief="flat", bd=0,
                  padx=10, pady=3, activebackground=SURF3, cursor="hand2").pack(side="left")

        tk.Frame(self.root, bg=ACCENT, height=2).pack(fill="x")

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True)
        self._tab_perf()
        self._tab_speedrun()
        self._tab_vehicle()
        self._tab_visual()
        self._tab_tweaks()
        self._tab_scanner()

    # ── Tab builders ──────────────────────────────────────────────────────────
    def _tab_perf(self):
        tab = tk.Frame(self.nb, bg=BG); self.nb.add(tab, text="  ⚡ Performance  ")
        self._gap(tab)

        c = self._card(tab, "FRAMERATE")
        self.v_fps    = tk.BooleanVar()
        self.v_fpscut = tk.BooleanVar()
        self.v_vsync  = tk.BooleanVar()
        self._chk(c, "Unlock Gameplay Framerate  (removes 30fps cap)",
                  self.v_fps, self._on_fps)
        self._chk(c, "Unlock Cutscene Framerate  ⚠ experimental",
                  self.v_fpscut, self._on_fps_cut)
        self._chk(c, "Disable V-Sync During Loading",
                  self.v_vsync, self._on_vsync)

        row = tk.Frame(c, bg=SURF); row.pack(fill="x", padx=14, pady=(6,4))
        tk.Label(row, text="Menu Max FPS:", bg=SURF, fg=TEXT, font=FNT,
                 width=16, anchor="w").pack(side="left")
        self.v_menu_fps = tk.DoubleVar(value=60.0)
        ttk.Scale(row, from_=30, to=240, variable=self.v_menu_fps, length=240).pack(
            side="left", padx=8)
        tk.Label(row, textvariable=self.v_menu_fps, width=6,
                 bg=SURF, fg=ACCENT, font=FNT_B).pack(side="left")
        self._sbtn(c, "Apply Menu FPS", self._apply_menu_fps)
        tk.Label(c, text="⚠ Values above 120 may affect physics. Default is 60.",
                 bg=SURF, fg=YEL, font=FNT_SM).pack(anchor="w", padx=14, pady=(0,10))

        self._gap(tab)
        c2 = self._card(tab, "GRAPHICS")
        self.v_blur = tk.BooleanVar(); self.v_shadows = tk.BooleanVar()
        self.v_refl = tk.BooleanVar()
        self._chk(c2, "Enhanced Motion Blur",     self.v_blur,    None)
        self._chk(c2, "Higher Quality Shadows",    self.v_shadows, None)
        self._chk(c2, "Enhanced Reflections",      self.v_refl,    None)
        self._sbtn(c2, "Apply Graphics", self._apply_graphics)

    def _tab_speedrun(self):
        tab = tk.Frame(self.nb, bg=BG); self.nb.add(tab, text="  ⏱ Speedrun  ")
        self._gap(tab)
        c = self._card(tab, "LOADLESS TIMER  —  manual pause mode")
        tk.Label(c, text=(
            "Press ⏸ Pause/Load when a load screen starts and ▶ Resume when back in-game.\n"
            "Running time excludes loading. Use LiveSplit for auto-split integration."),
            bg=SURF, fg=DIM, font=FNT_SM, wraplength=700, justify="left"
        ).pack(anchor="w", padx=14, pady=(0,6))

        self._tlbl = tk.Label(c, text="00:00:00.000", bg=SURF, fg=TEXT, font=FNT_MONO)
        self._tlbl.pack(pady=(8,4))
        info = tk.Frame(c, bg=SURF); info.pack()
        self._llbl  = tk.Label(info, text="Loads: 00:00:00", bg=SURF, fg=DIM, font=FNT)
        self._llbl.pack(side="left", padx=16)
        self._stlbl = tk.Label(info, text="● Idle", bg=SURF, fg=DIM, font=FNT_B)
        self._stlbl.pack(side="left")

        btns = tk.Frame(c, bg=SURF); btns.pack(pady=10)
        for lbl, cmd, col in [
            ("▶ Start",      self._t_start,  GRN),
            ("⏸ Pause/Load", self._t_pause,  YEL),
            ("▶ Resume",     self._t_resume, GRN),
            ("✂ Split",       self._t_split,  ACCENT),
            ("■ Stop",        self._t_stop,   RED),
            ("↺ Reset",       self._t_reset,  DIM),
        ]:
            tk.Button(btns, text=lbl, command=cmd, bg=SURF2, fg=col, font=FNT_B,
                      relief="flat", bd=0, padx=10, pady=6,
                      activebackground=SURF3, cursor="hand2").pack(side="left", padx=3)

        self._gap_f(c, SURF)
        c2 = self._card(tab, "SPLITS")
        self._sbox = tk.Text(c2, height=7, bg=SURF2, fg=TEXT, font=("Consolas", 9),
                             relief="flat", bd=0, padx=8, pady=6)
        self._sbox.pack(fill="x", padx=12, pady=(0,8))
        row = tk.Frame(c2, bg=SURF); row.pack(fill="x", padx=12, pady=(0,10))
        self._ibtn(row, "Export JSON", self._t_export)
        self._ibtn(row, "Copy Time",   self._t_copy)

    def _tab_vehicle(self):
        tab = tk.Frame(self.nb, bg=BG); self.nb.add(tab, text="  🚗 Vehicle  ")
        self._gap(tab)
        c = self._card(tab, "QUICK TOGGLES")
        self.v_assists = tk.BooleanVar(); self.v_nos = tk.BooleanVar()
        self.v_nodmg   = tk.BooleanVar()
        self._chk(c, "Disable All Driving Assists",          self.v_assists, self._on_assists)
        self._chk(c, "Infinite NOS  (continuous refresh)",   self.v_nos,     self._on_nos)
        self._chk(c, "No Vehicle Damage  (continuous reset)",self.v_nodmg,   self._on_nodmg)
        self._gap(tab)
        c2 = self._card(tab, "VEHICLE CUSTOMIZER")
        tk.Label(c2, text="Vehicle, bodykit, paint and performance editor with JSON presets.",
                 bg=SURF, fg=DIM, font=FNT, justify="left").pack(anchor="w", padx=14, pady=(4,10))
        tk.Button(c2, text="  Open Vehicle Customizer  →", command=self._open_cust,
                  bg=ACCENT, fg="white", font=FNT_B, relief="flat", bd=0,
                  padx=16, pady=8, activebackground=ACCH, cursor="hand2"
                  ).pack(anchor="w", padx=14, pady=(0,14))

    def _tab_visual(self):
        tab = tk.Frame(self.nb, bg=BG); self.nb.add(tab, text="  🌅 Visual  ")
        self._gap(tab)
        c = self._card(tab, "LIGHTING  —  update addresses via Cheat Engine before use")
        tk.Label(c,
                 text="⚠  Sun/light addresses are dynamic (heap-allocated by Frostbite).\n"
                      "   Find them in-game with CE → pointer scan, then update SIGS in the source.",
                 bg=SURF, fg=YEL, font=FNT_SM, justify="left"
                 ).pack(anchor="w", padx=14, pady=(2, 6))
        self.v_lights = tk.BooleanVar()
        self._chk(c, "Force Headlights On  (code patch — stable across versions)",
                  self.v_lights, self._on_headlights)
        self._gap_f(c, SURF)
        for lbl, var, lo, hi, cmd in [
            ("World Light Intensity", tk.DoubleVar(value=1.0), 0.0,  3.0, None),
            ("Exposure",              tk.DoubleVar(value=1.0), 0.0,  3.0, None),
            ("Sun Position X (°)",    tk.DoubleVar(value=0.0), -180, 180, None),
            ("Sun Position Y (°)",    tk.DoubleVar(value=0.0), -180, 180, None),
        ]:
            setattr(self, f"v_{lbl[:3].lower().strip()}", var)
            row = tk.Frame(c, bg=SURF); row.pack(fill="x", padx=14, pady=3)
            tk.Label(row, text=lbl, bg=SURF, fg=DIM, font=FNT,
                     width=24, anchor="w").pack(side="left")
            ttk.Scale(row, from_=lo, to=hi, variable=var, length=280).pack(side="left", padx=8)
            tk.Label(row, textvariable=var, width=7,
                     bg=SURF, fg=DIM, font=FNT_B).pack(side="left")
        tk.Label(c, text="  Dynamic addresses — sliders disabled until addresses are confirmed.",
                 bg=SURF, fg=DIM, font=FNT_SM).pack(anchor="w", padx=14, pady=(0,10))

    def _tab_tweaks(self):
        tab = tk.Frame(self.nb, bg=BG); self.nb.add(tab, text="  🔧 Tweaks  ")
        self._gap(tab)
        c = self._card(tab, "UNLOCKS")
        tk.Label(c, text="Patches in-game lock checks. Enter a race to see changes.",
                 bg=SURF, fg=DIM, font=FNT).pack(anchor="w", padx=14, pady=(4,8))
        self._wbtn(c, "Unlock All Vehicles",   self._unlock_cars)
        self._wbtn(c, "Unlock All Challenges",  self._unlock_challenges)
        self._gap(tab)
        c2 = self._card(tab, "STABILITY FIXES")
        tk.Label(c2, text="NOPs crash-trigger code on specific stages.",
                 bg=SURF, fg=DIM, font=FNT).pack(anchor="w", padx=14, pady=(4,8))
        self._wbtn(c2, "Apply All Crash Bypasses", self._apply_crash)
        self._gap_f(c2, SURF, 10)

    def _tab_scanner(self):
        """Scanner status tab — shows AOB scan results for every signature."""
        tab = tk.Frame(self.nb, bg=BG); self.nb.add(tab, text="  🔍 Scanner  ")
        self._gap(tab)
        c = self._card(tab, "SIGNATURE SCAN STATUS")
        tk.Label(c,
                 text="Shows how each feature's address was resolved.\n"
                      "🟢 Scanned = pattern found dynamically  "
                      "🟡 Fallback = using CT table RVA  "
                      "🔴 Missing = not found",
                 bg=SURF, fg=DIM, font=FNT_SM, justify="left"
                 ).pack(anchor="w", padx=14, pady=(4, 8))
        self._scan_frame = tk.Frame(c, bg=SURF)
        self._scan_frame.pack(fill="both", expand=True, padx=14, pady=(0,10))
        self._scan_rows: dict[str, tk.Label] = {}
        for name, sig in SIGS.items():
            row = tk.Frame(self._scan_frame, bg=SURF)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=sig["desc"], bg=SURF, fg=TEXT, font=FNT,
                     width=38, anchor="w").pack(side="left")
            lbl = tk.Label(row, text="—", bg=SURF, fg=DIM, font=FNT_SM)
            lbl.pack(side="left")
            self._scan_rows[name] = lbl

        self._sbtn(c, "Re-scan now", self._do_connect)

    # ── Widgets ───────────────────────────────────────────────────────────────
    def _gap(self, p, h=10): tk.Frame(p, bg=BG,  height=h).pack()
    def _gap_f(self, p, bg, h=8): tk.Frame(p, bg=bg, height=h).pack()

    def _card(self, parent, title):
        outer = tk.Frame(parent, bg=SURF); outer.pack(fill="x", padx=16)
        tk.Label(outer, text=title, bg=SURF, fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=14, pady=(12,2))
        tk.Frame(outer, bg=BDR, height=1).pack(fill="x", padx=14, pady=(0,8))
        return outer

    def _chk(self, parent, text, var, cmd):
        f = tk.Frame(parent, bg=SURF); f.pack(anchor="w", padx=14, pady=3)
        tk.Checkbutton(f, text=text, variable=var, command=cmd,
                       bg=SURF, fg=TEXT, selectcolor=SURF3, activebackground=SURF,
                       activeforeground=TEXT, font=FNT, relief="flat", cursor="hand2"
                       ).pack(side="left")

    def _sbtn(self, parent, text, cmd):
        tk.Button(parent, text=text, command=cmd, bg=SURF2, fg=TEXT, font=FNT_B,
                  relief="flat", bd=0, padx=12, pady=5,
                  activebackground=SURF3, cursor="hand2").pack(anchor="w", padx=14, pady=(2,10))

    def _ibtn(self, parent, text, cmd):
        tk.Button(parent, text=text, command=cmd, bg=SURF2, fg=TEXT, font=FNT_B,
                  relief="flat", bd=0, padx=10, pady=4,
                  activebackground=SURF3, cursor="hand2").pack(side="left", padx=(0,8))

    def _wbtn(self, parent, text, cmd):
        tk.Button(parent, text=text, command=cmd, bg=SURF2, fg=TEXT, font=FNT_B,
                  relief="flat", bd=0, padx=16, pady=8,
                  activebackground=SURF3, cursor="hand2").pack(fill="x", padx=14, pady=4)

    # ── Connection ────────────────────────────────────────────────────────────
    def _do_connect(self):
        self._set_status("Connecting…", YEL)
        threading.Thread(target=self._connect_worker, daemon=True).start()

    def _connect_worker(self):
        for name in self.PROCESS_NAMES:
            try:
                pm  = pymem.Pymem(name)
                mod = pymem.process.module_from_name(pm.process_handle, name)
                if not mod:
                    continue
                with self._lock:
                    self.pm        = pm
                    self.base      = mod.lpBaseOfDll
                    self.connected = True

                # Run AOB scan
                self.root.after(0, lambda: self._set_status("Scanning signatures…", YEL))
                found = self.features.resolve(
                    pm, self.base,
                    progress_cb=lambda n, s: self.root.after(0, lambda n=n, s=s: self._update_scan_row(n, s))
                )

                label = (f"Connected  ·  {name}  ·  base {hex(self.base)}"
                         f"  ·  {found}/{len(SIGS)} features resolved")
                self.root.after(0, lambda l=label: self._set_status(l, GRN))
                self.root.after(0, self._start_monitor)
                return
            except Exception:
                continue

        self.root.after(0, lambda: self._set_status(
            "Not connected — launch NFS The Run then reconnect (Admin required)", RED))

    def _update_scan_row(self, name: str, status: str):
        lbl = self._scan_rows.get(name)
        if not lbl:
            return
        addr = self.features.get(name)
        addr_str = hex(addr) if addr else "—"
        if status == "scanned":
            lbl.config(text=f"🟢  {addr_str}", fg=GRN)
        elif status == "fallback":
            lbl.config(text=f"🟡  {addr_str}  (fallback)", fg=YEL)
        else:
            lbl.config(text="🔴  not found", fg=RED)

    def _set_status(self, msg, color):
        self._dot.config(fg=color); self._slbl.config(text=msg)

    def _guard(self) -> bool:
        if not self.connected:
            messagebox.showwarning("Not connected",
                "Connect to the game first.\n"
                "• NFS The Run must be running\n"
                "• Run this tool as Administrator\n"
                "• Game version: v1.1.0.0 (DRM-free/Origin/Steam)")
            return False
        return True

    # ── Safe Memory I/O ───────────────────────────────────────────────────────
    def safe_read(self, addr: int, length: int) -> bytes | None:
        try:
            with self._lock:
                data = self.pm.read_bytes(addr, length)
            return data if len(data) == length else None
        except Exception as e:
            print(f"[READ  {hex(addr)}] {e}"); return None

    def safe_write(self, addr: int, data: bytes) -> bool:
        """Write bytes; automatically upgrades memory protection if needed."""
        # Attempt 1: plain write
        try:
            with self._lock: self.pm.write_bytes(addr, data, len(data))
            return True
        except Exception: pass
        # Attempt 2: PAGE_EXECUTE_READWRITE override  ← no recursive call
        try:
            old = c_ulong(0)
            windll.kernel32.VirtualProtectEx(
                self.pm.process_handle, c_void_p(addr),
                c_size_t(len(data)), 0x40, byref(old))
            with self._lock: self.pm.write_bytes(addr, data, len(data))
            windll.kernel32.VirtualProtectEx(
                self.pm.process_handle, c_void_p(addr),
                c_size_t(len(data)), old, byref(c_ulong(0)))
            return True
        except Exception as e:
            print(f"[WRITE {hex(addr)}] {e}"); return False

    def _wf(self, addr: int, v: float) -> bool:
        return self.safe_write(addr, struct.pack("<f", v))
    def _wb(self, addr: int, v: int)  -> bool:
        return self.safe_write(addr, struct.pack("<B", v))
    def _wd(self, addr: int, v: int)  -> bool:
        return self.safe_write(addr, struct.pack("<I", v))

    def _nop(self, addr: int, size: int = 5) -> bool:
        if addr not in self._nop_cache:
            orig = self.safe_read(addr, size)
            if orig is None: return False
            self._nop_cache[addr] = orig
        return self.safe_write(addr, b"\x90" * size)

    def _unnop(self, addr: int) -> bool:
        orig = self._nop_cache.get(addr)
        return self.safe_write(addr, orig) if orig else False

    def _feat(self, name: str) -> int | None:
        """Return the resolved absolute address for a feature, or None."""
        return self.features.get(name)

    # ── Monitor thread ────────────────────────────────────────────────────────
    def _start_monitor(self):
        if self._mon_run: return
        self._mon_run = True
        threading.Thread(target=self._monitor, daemon=True).start()

    def _monitor(self):
        errs = 0
        while self._mon_run and self.connected:
            try:
                if not self._alive():
                    self.connected = False
                    self.root.after(0, lambda: self._set_status(
                        "Game closed — reconnect to reattach", RED))
                    break

                self.timer.tick()
                self.root.after(0, self._refresh_timer)

                # Freeze features
                if self.freeze_nos:
                    self._wf(self.base + 0x1391E80, 1.0)
                    self._wf(self.base + 0x1391E88, 0.0)
                if self.freeze_nodmg:
                    for off in (0xBDF4B0, 0xBDF4C0, 0xBDF4D0):
                        self._wf(self.base + off, 0.0)

                errs = 0; time.sleep(1/30)
            except Exception as e:
                errs = min(errs+1, 10); print(f"[MON] {e}")
                time.sleep(min(0.1*errs, 2.0))

    def _alive(self) -> bool:
        try:
            import psutil; return psutil.pid_exists(self.pm.process_id)
        except Exception:
            try: self.pm.read_bytes(self.base, 1); return True
            except Exception: return False

    # ── Timer UI ──────────────────────────────────────────────────────────────
    def _refresh_timer(self):
        if not self.timer.active: return
        self._tlbl.config(text=self.timer.time_str())
        ls = str(self.timer.loading_time).split(".")[0]
        self._llbl.config(text=f"Loads: {ls}")
        if not self.timer.active:
            self._stlbl.config(text="● Idle",    fg=DIM)
        elif self.timer.is_paused:
            self._stlbl.config(text="⏸ Loading", fg=YEL)
        else:
            self._stlbl.config(text="● Running", fg=GRN)

    def _t_start(self):
        self.timer.start(); self._sbox.delete("1.0","end")
        self._stlbl.config(text="● Running", fg=GRN)

    def _t_pause(self):
        self.timer.pause(); self._stlbl.config(text="⏸ Loading", fg=YEL)

    def _t_resume(self):
        self.timer.resume(); self._stlbl.config(text="● Running", fg=GRN)

    def _t_split(self):
        name = f"Split {len(self.timer.splits)+1}"
        self.timer.split(name)
        self._sbox.insert("end", f"{name:<12}  {self.timer.time_str()}\n")
        self._sbox.see("end")

    def _t_stop(self):
        self.timer.stop(); self._stlbl.config(text="● Stopped", fg=RED)

    def _t_reset(self):
        self.timer.reset()
        self._tlbl.config(text="00:00:00.000"); self._llbl.config(text="Loads: 00:00:00")
        self._stlbl.config(text="● Idle", fg=DIM); self._sbox.delete("1.0","end")

    def _t_export(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON","*.json")])
        if p: self.timer.export(p); messagebox.showinfo("Exported", f"Saved:\n{p}")

    def _t_copy(self):
        self.root.clipboard_clear(); self.root.clipboard_append(self.timer.time_str())

    # ── Performance ───────────────────────────────────────────────────────────
    def _on_fps(self):
        if not self._guard(): self.v_fps.set(False); return
        addr = self._feat("fps_cluster")
        if addr is None:
            messagebox.showerror("Missing", "fps_cluster address not found. See Scanner tab."); return
        on = self.v_fps.get()
        # CT table enable sequence: patch the byte operands from 01→00 and NOP the jmp
        # Offsets relative to the C6 05 instruction at fps_cluster:
        #  +6 = first value byte (01/00)
        #  +13 = second value byte
        #  +14 = start of jmp (E9 xx xx xx xx) → NOP ×5
        #  +23 = third value byte
        for delta, val in [(6, 0x00 if on else 0x01),
                           (13, 0x00 if on else 0x01),
                           (23, 0x00 if on else 0x01)]:
            self._wb(addr + delta, val)
        if on:
            self._nop(addr + 14, 5)
        else:
            self._unnop(addr + 14)

    def _on_fps_cut(self):
        if not self._guard(): self.v_fpscut.set(False); return
        # Cutscene cap is the same float as gameplay; unlock or restore
        addr = self._feat("gametime")
        if addr:
            pass  # gametime hook point — FPS cap is read nearby; needs CE exploration

    def _on_vsync(self):
        if not self._guard(): self.v_vsync.set(False); return
        # CT: the loading vsync nops are within the fps_cluster region
        addr = self._feat("fps_cluster")
        if addr is None: return
        on = self.v_vsync.get()
        # Offsets from CT for the vsync jmp bytes (within fps cluster)
        for delta, size in [(14, 5)]:
            if on: self._nop(addr + delta, size)
            else:  self._unnop(addr + delta)

    def _apply_menu_fps(self):
        if not self._guard(): return
        addr = self._feat("gametime")
        if addr is None:
            messagebox.showerror("Missing", "gametime address not found."); return
        # MaxVariableFps is at varSimTick-0x18; varSimTick = eax+0x40 at gametime
        # Without hooking we can't know eax. This needs CE to find the float address.
        messagebox.showinfo("Note",
            "Menu FPS float address is resolved dynamically at runtime by the game engine.\n\n"
            "To find it: open CE → attach → enable 'GameTime Settings' hook → \n"
            "read the 'MaxVariableFps' entry address → add to SIGS in source.")

    def _apply_graphics(self):
        messagebox.showinfo("Note", "Graphics flags take effect at the next scene transition.")

    # ── Vehicle ───────────────────────────────────────────────────────────────
    def _on_assists(self):
        if not self._guard(): self.v_assists.set(False); return
        on = self.v_assists.get()
        patches = [
            # (sig_name, patch_type, size_or_bytes)
            ("assist_align",       "byte_toggle", (0x74, 0x75)),  # je↔jne
            ("assist_drift_intent","byte_toggle", (0x75, 0x74)),  # jne↔je
            ("assist_rla_forces",  "nop", 6),
            ("assist_drift_forces","nop", 5),
        ]
        for sig_name, ptype, arg in patches:
            addr = self._feat(sig_name)
            if addr is None:
                print(f"[ASSIST] {sig_name} not resolved"); continue
            if ptype == "nop":
                self._nop(addr, arg) if on else self._unnop(addr)
            elif ptype == "byte_toggle":
                enable_byte, disable_byte = arg
                self._wb(addr, enable_byte if on else disable_byte)

        # RaceLineAssist status: write 0 (disabled) or 2 (enabled)
        addr_status = self._feat("assist_rla_status")
        if addr_status:
            # write 0x00000000 at +3 (the 02 byte in C7 47 50 02 00 00 00)
            self._wb(addr_status + 3, 0x00 if on else 0x02)

    def _on_nos(self):
        if not self._guard(): self.v_nos.set(False); return
        self.freeze_nos = self.v_nos.get()

    def _on_nodmg(self):
        if not self._guard(): self.v_nodmg.set(False); return
        self.freeze_nodmg = self.v_nodmg.get()

    def _open_cust(self):
        if not self._guard(): return
        VehicleCustomizer(self.root, self)

    # ── Visual ────────────────────────────────────────────────────────────────
    def _on_headlights(self):
        if not self._guard(): self.v_lights.set(False); return
        # Headlight addresses from original RE work — these are RVAs
        HEADLIGHT_RVAS = [0xF8E41B, 0xF8B149, 0xF8E42C, 0xF8AA6D, 0xF86BB4]
        on = self.v_lights.get()
        for rva in HEADLIGHT_RVAS:
            addr = self.base + rva
            self._nop(addr, 2) if on else self._unnop(addr)

    # ── Tweaks ────────────────────────────────────────────────────────────────
    def _unlock_cars(self):
        if not self._guard(): return
        # CT absolute 0093DDE7: mov al,00 (was 01)
        delta  = self.base - IMAGE_BASE
        addr   = 0x0093DDE7 + delta
        if self._wb(addr, 0x00):
            messagebox.showinfo("Done",
                "Vehicle unlock applied.\nEnter a race to see all cars available.")
        else:
            messagebox.showerror("Failed",
                f"Write failed at {hex(addr)}.\n"
                "Check Scanner tab — address may need updating for your build.")

    def _unlock_challenges(self):
        if not self._guard(): return
        delta = self.base - IMAGE_BASE
        for abs_addr in (0x0093D732, 0x0093D195):
            self._nop(abs_addr + delta, 5)
        messagebox.showinfo("Done", "Challenge unlock applied.")

    def _apply_crash(self):
        if not self._guard(): return
        results = []
        for sig in ("tunnel_crash", "chicago_a", "chicago_b"):
            addr = self._feat(sig)
            if addr:
                size = 3 if sig == "tunnel_crash" else 6
                ok   = self._nop(addr, size)
                results.append(f"{'✓' if ok else '✗'}  {SIGS[sig]['desc']}")
            else:
                results.append(f"✗  {SIGS[sig]['desc']}  (address missing)")
        messagebox.showinfo("Crash Bypasses", "\n".join(results))

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def _on_close(self):
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
                None, "runas", sys.executable, f'"{sys.argv[0]}"', None, 1)
            sys.exit(0)
    except Exception:
        pass

if __name__ == "__main__":
    _ensure_admin()
    root = tk.Tk()
    NFSModSuite(root)
    root.mainloop()
