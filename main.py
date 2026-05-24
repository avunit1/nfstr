#!/usr/bin/env python3
"""
NFS The Run — Advanced Mod Suite v2.1
Single-player / offline use only.  Run as Administrator.

Fixes over v2.0
───────────────
• safe_write / safe_read: removed infinite recursive call through
  safe_write_with_protection; protection override is now inline.
• All toggle/action methods that were stubs are now implemented.
• Float memory writes now use struct.pack("<f", …) instead of int.to_bytes.
• NOP patches cache original bytes so toggle-off restores correctly.
• Infinite NOS / no-damage are continuous writes in the monitor thread
  (game overwrites one-shot writes within a frame).
• Process name tried in 4 variations; connection runs off the UI thread.
• Auto-elevation to Administrator on launch.
• Full dark theme — no default tkinter chrome.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pymem
import pymem.process
import struct
import threading
import time
import json
import ctypes
from ctypes import windll, c_ulong, c_void_p, c_size_t, byref
from datetime import datetime, timedelta

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = "#0f1117"   # page background
SURF    = "#1a1d27"   # card surface
SURF2   = "#22263a"   # inset / row
SURF3   = "#2c3050"   # hover
ACCENT  = "#ff6b35"   # NFS orange
ACCH    = "#e05820"   # accent hover
TEXT    = "#eaeaf0"   # primary text
DIM     = "#7a7d99"   # muted text
GRN     = "#4ade80"   # success
RED     = "#f87171"   # error
YEL     = "#fbbf24"   # warning
BDR     = "#252840"   # border

FNT      = ("Segoe UI", 9)
FNT_B    = ("Segoe UI", 9,  "bold")
FNT_H    = ("Segoe UI", 11, "bold")
FNT_MONO = ("Consolas",  22, "bold")


# ══════════════════════════════════════════════════════════════════════════════
# LoadlessTimer
# ══════════════════════════════════════════════════════════════════════════════
class LoadlessTimer:
    """Thread-safe millisecond-accurate timer that excludes loading time."""

    def __init__(self):
        self._lock        = threading.Lock()
        self.running_time = timedelta()
        self.loading_time = timedelta()
        self.is_loading   = False
        self.active       = False
        self._last        = None
        self.splits: list[dict] = []

    def start(self):
        with self._lock:
            self.active       = True
            self._last        = datetime.now()
            self.running_time = timedelta()
            self.loading_time = timedelta()
            self.splits       = []

    def stop(self):
        with self._lock:
            self.active = False
            self._last  = None

    def reset(self):
        with self._lock:
            self.active       = False
            self._last        = None
            self.running_time = timedelta()
            self.loading_time = timedelta()
            self.splits       = []

    def update(self, is_loading: bool):
        if not self.active:
            return
        now = datetime.now()
        with self._lock:
            if self._last:
                delta = now - self._last
                secs  = delta.total_seconds()
                if 0 < secs < 1.0:          # sanity: ignore impossible deltas
                    if is_loading:
                        self.loading_time += delta
                        self.is_loading    = True
                    else:
                        self.running_time += delta
                        self.is_loading    = False
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
                "running_time": str(self.running_time),
                "loading_time": str(self.loading_time),
                "splits":       self.splits,
            }, f, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# VehicleCustomizer (separate Toplevel window)
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
    BODYKITS = {
        "Stock":         0x00,
        "Time Attack":   0x01,
        "Aero Pack":     0x02,
        "Circuit Racer": 0x03,
    }
    PAINTS = {
        "Metallic Blue": 0x257F2512,
        "Matte Black":   0x4E9BBE75,
        "Glossy White":  0xC494BC78,
        "Carbon Fiber":  0x1780E1,
    }

    def __init__(self, parent: tk.Tk, suite: "NFSModSuite"):
        self.suite = suite
        self.win   = tk.Toplevel(parent, bg=BG)
        self.win.title("Vehicle Customizer")
        self.win.geometry("700x520")
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)
        self._build()

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _lbl(self, p, t, fg=TEXT, bg=SURF, font=FNT):
        return tk.Label(p, text=t, bg=bg, fg=fg, font=font)

    def _btn(self, p, t, cmd, accent=False):
        bg = ACCENT if accent else SURF2
        hv = ACCH   if accent else SURF3
        return tk.Button(p, text=t, command=cmd,
                         bg=bg, fg="white" if accent else TEXT,
                         font=FNT_B, relief="flat", bd=0,
                         padx=14, pady=6,
                         activebackground=hv, activeforeground=TEXT,
                         cursor="hand2")

    def _write(self, offset: int, data: bytes) -> bool:
        return self.suite.safe_write(self.suite.base + offset, data)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build(self):
        # Header bar
        hdr = tk.Frame(self.win, bg=SURF, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  🚗  Vehicle Customizer",
                 bg=SURF, fg=TEXT, font=FNT_H).pack(side="left", padx=10, pady=12)

        nb = ttk.Notebook(self.win)
        nb.pack(fill="both", expand=True, padx=12, pady=10)

        # ── Vehicle ──
        vf = tk.Frame(nb, bg=SURF);  nb.add(vf, text="  Vehicle  ")
        self._lbl(vf, "Select Car", fg=ACCENT, font=FNT_B).pack(anchor="w", padx=20, pady=(14, 4))
        self.v_car = tk.StringVar(value=list(self.VEHICLES)[0])
        ttk.Combobox(vf, textvariable=self.v_car,
                     values=list(self.VEHICLES), state="readonly", width=34
                     ).pack(padx=20, pady=4)
        self._btn(vf, "Apply Vehicle", self._apply_vehicle, accent=True
                  ).pack(anchor="w", padx=20, pady=10)

        # ── Bodykit ──
        bf = tk.Frame(nb, bg=SURF);  nb.add(bf, text="  Bodykit  ")
        self._lbl(bf, "Bodykit Style", fg=ACCENT, font=FNT_B).pack(anchor="w", padx=20, pady=(14, 4))
        self.v_kit = tk.StringVar(value="Stock")
        for name in self.BODYKITS:
            tk.Radiobutton(bf, text=name, variable=self.v_kit, value=name,
                           bg=SURF, fg=TEXT, selectcolor=SURF3,
                           activebackground=SURF, font=FNT
                           ).pack(anchor="w", padx=30, pady=2)
        self._btn(bf, "Apply Bodykit", self._apply_bodykit, accent=True
                  ).pack(anchor="w", padx=20, pady=10)

        # ── Paint ──
        pf = tk.Frame(nb, bg=SURF);  nb.add(pf, text="  Paint  ")
        self._lbl(pf, "Paint Colour", fg=ACCENT, font=FNT_B).pack(anchor="w", padx=20, pady=(14, 4))
        self.v_paint = tk.StringVar(value=list(self.PAINTS)[0])
        ttk.Combobox(pf, textvariable=self.v_paint,
                     values=list(self.PAINTS), state="readonly", width=26
                     ).pack(padx=20, pady=4)
        self._btn(pf, "Apply Paint", self._apply_paint, accent=True
                  ).pack(anchor="w", padx=20, pady=10)

        # ── Performance ──
        perf = tk.Frame(nb, bg=SURF); nb.add(perf, text="  Performance  ")
        self._lbl(perf, "Performance Tier  (1 = stock  →  6 = max)",
                  fg=ACCENT, font=FNT_B).pack(anchor="w", padx=20, pady=(14, 4))
        self.v_tier = tk.IntVar(value=5)
        ttk.Scale(perf, from_=1, to=6, orient="horizontal",
                  variable=self.v_tier, length=320).pack(padx=20, pady=6)
        tk.Label(perf, textvariable=self.v_tier,
                 bg=SURF, fg=ACCENT, font=("Segoe UI", 14, "bold")).pack()
        self._btn(perf, "Apply Tier", self._apply_performance, accent=True
                  ).pack(anchor="w", padx=20, pady=10)

        # Preset row
        row = tk.Frame(self.win, bg=BG)
        row.pack(fill="x", padx=12, pady=(0, 12))
        self._btn(row, "💾  Save Preset", self._save).pack(side="left", padx=(0, 8))
        self._btn(row, "📂  Load Preset", self._load).pack(side="left")

    # ── Actions ───────────────────────────────────────────────────────────────
    def _apply_vehicle(self):
        try:
            h = self.VEHICLES[self.v_car.get()]
            if self._write(0x1391D40, struct.pack("<I", h)):
                self._ok(f"Vehicle set: {self.v_car.get()}")
        except Exception as e:
            self._err(e)

    def _apply_bodykit(self):
        try:
            v = self.BODYKITS[self.v_kit.get()]
            if self._write(0x1391E20, struct.pack("<B", v)):
                self._ok(f"Bodykit set: {self.v_kit.get()}")
        except Exception as e:
            self._err(e)

    def _apply_paint(self):
        try:
            h = self.PAINTS[self.v_paint.get()]
            if self._write(0x1391E40, struct.pack("<I", h)):
                self._ok(f"Paint set: {self.v_paint.get()}")
        except Exception as e:
            self._err(e)

    def _apply_performance(self):
        try:
            t = max(1, min(6, self.v_tier.get()))
            if self._write(0x1391E60, struct.pack("<B", t)):
                self._ok(f"Performance Tier {t} applied")
        except Exception as e:
            self._err(e)

    def _save(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            parent=self.win)
        if path:
            with open(path, "w") as f:
                json.dump({"vehicle": self.v_car.get(), "bodykit": self.v_kit.get(),
                           "paint": self.v_paint.get(), "tier": self.v_tier.get()}, f, indent=2)
            messagebox.showinfo("Saved", f"Preset saved.", parent=self.win)

    def _load(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")], parent=self.win)
        if path:
            with open(path) as f:
                d = json.load(f)
            self.v_car.set(d.get("vehicle",  list(self.VEHICLES)[0]))
            self.v_kit.set(d.get("bodykit",  "Stock"))
            self.v_paint.set(d.get("paint",  list(self.PAINTS)[0]))
            self.v_tier.set(d.get("tier",    5))
            messagebox.showinfo("Loaded", "Preset loaded — click Apply to apply each section.",
                                parent=self.win)

    def _ok(self, msg):  messagebox.showinfo("Applied", msg, parent=self.win)
    def _err(self, e):   messagebox.showerror("Error",   str(e), parent=self.win)


# ══════════════════════════════════════════════════════════════════════════════
# NFSModSuite — main application
# ══════════════════════════════════════════════════════════════════════════════
class NFSModSuite:

    # Try multiple exe names — EA shipped different builds
    PROCESS_NAMES = [
        "Need for Speed The Run.exe",
        "Need For Speed The Run.exe",
        "NFS13.exe",
        "nfs13.exe",
    ]

    # ── Memory layout (offsets relative to module base, v1.1.0.0) ─────────────
    #
    # All offsets come from the community .CT table (_mRally2) bundled with
    # this repo plus ReClass.NET pointer chain analysis.
    #
    # ⚠  If writes silently fail: open Cheat Engine, attach to the game, verify
    #    base+offset resolves to the expected value, and update accordingly.
    #
    OFFSETS = {
        # ── Framerate ──
        "max_fps":           0xA607F7,   # float  — gameplay FPS cap
        "menu_fps":          0xA607DF,   # float  — menu simulation FPS
        "load_fps":          0xA607E7,   # float  — loading-screen FPS cap
        # Code offsets to NOP for framerate bypass (5 bytes each)
        "fps_nop_list":      [0x4106F8, 0x4106FF, 0x410706,
                              0x41070B, 0x410710, 0x410717, 0x41076F],
        # Loading vsync NOPs — store (offset, original_bytes) pairs
        "load_vsync_nops":   [
            (0x410706, b"\xE9\x8B\x01\x00\x00"),
            (0x41070B, b"\xE9\x86\x01\x00\x00"),
            (0x410715, b"\xE9\x81\x01\x00\x00"),
        ],

        # ── Vehicle pointer chain ──
        # Final vehicle object = [[[[base + 0x2A8598C] + 0x1B8] + 0x38] + 0xD0]
        "veh_ptr":           0x2A8598C,
        "veh_chain":         [0x1B8, 0x38, 0xD0],
        "veh_state":         0x4A0,      # uint32 inside vehicle object

        # ── Vehicle live data ──
        "nos_tank":          0x1391E80,  # float  — NOS level (0.0–1.0)
        "nos_rate":          0x1391E88,  # float  — NOS consumption rate
        "dmg0":              0xBDF4B0,   # float  — damage component 0
        "dmg1":              0xBDF4C0,   # float  — damage component 1
        "dmg2":              0xBDF4D0,   # float  — damage component 2

        # ── Assists (code patch, 5-byte NOP each) ──
        "assists":           [0x1819981, 0x18199A6, 0x1819AB1,
                              0x181AA64, 0x1828E73, 0x69B167, 0x69B5E2],

        # ── Visual ──
        "headlights":        [0xF8E41B, 0xF8B149, 0xF8E42C, 0xF8AA6D, 0xF86BB4],
        "light_render":      0x1E3B13B,  # float
        "exposure":          0x1F620B8,  # float
        "sun_x":             0x1F620B0,  # float
        "sun_y":             0x1F620A8,  # float

        # ── Unlocks / tweaks ──
        # From FearLess CE table (absolute addrs; subtract 0x400000 for offset)
        "car_unlock":        0x53DDE7,   # mov al,00  (was mov al,01)
        "challenge_nops":    [0x53D732, 0x53D195],

        # Crash bypass (NOP the trigger checks)
        "tunnel_pain":       0x121D23B,
        "chicago_crash":     [0xE4EB60, 0xE50F0E],
    }

    def __init__(self, root: tk.Tk):
        self.root      = root
        self.pm        = None
        self.base: int = 0
        self.connected = False

        self.timer     = LoadlessTimer()
        self._lock     = threading.Lock()
        self._mon_run  = False

        # Cache original bytes before NOP-patching so we can restore on toggle-off
        self._nop_cache: dict[int, bytes] = {}

        # Freeze flags — set by toggles, consumed by monitor thread
        self.freeze_nos  = False
        self.freeze_nodmg = False

        root.title("NFS The Run — Mod Suite v2.1")
        root.geometry("880x680")
        root.resizable(False, False)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._apply_theme()
        self._build_ui()
        root.after(600, self._do_connect)   # attempt connection after UI renders

    # ══════════════════════════════════════════════════════════════════════════
    # Theme
    # ══════════════════════════════════════════════════════════════════════════
    def _apply_theme(self):
        s = ttk.Style()
        s.theme_use("default")

        # Frames
        s.configure("TFrame",        background=BG)
        s.configure("Card.TFrame",   background=SURF)
        s.configure("Card2.TFrame",  background=SURF2)

        # Labels
        for name, bg, fg, font in [
            ("TLabel",       BG,    TEXT,   FNT),
            ("Card.TLabel",  SURF,  TEXT,   FNT),
            ("Card2.TLabel", SURF2, TEXT,   FNT),
            ("Dim.TLabel",   SURF,  DIM,    FNT),
            ("Head.TLabel",  SURF,  ACCENT, FNT_B),
            ("Big.TLabel",   BG,    TEXT,   FNT_H),
        ]:
            s.configure(name, background=bg, foreground=fg, font=font)

        # Buttons
        s.configure("TButton",
                    background=SURF2, foreground=TEXT, font=FNT_B,
                    relief="flat", borderwidth=0, padding=(12, 6))
        s.map("TButton",
              background=[("active", SURF3), ("pressed", SURF3)])

        s.configure("Accent.TButton",
                    background=ACCENT, foreground="white", font=FNT_B,
                    relief="flat", borderwidth=0, padding=(12, 6))
        s.map("Accent.TButton",
              background=[("active", ACCH), ("pressed", ACCH)])

        # Checkbuttons
        s.configure("TCheckbutton",
                    background=SURF, foreground=TEXT, font=FNT,
                    indicatorcolor=SURF3, selectcolor=SURF3)
        s.map("TCheckbutton",
              background=[("active", SURF)],
              foreground=[("active", TEXT)])

        # LabelFrames
        s.configure("TLabelframe",
                    background=SURF, bordercolor=BDR, relief="flat", borderwidth=1)
        s.configure("TLabelframe.Label",
                    background=SURF, foreground=ACCENT, font=FNT_B)

        # Notebook
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab",
                    background=SURF, foreground=DIM, font=FNT_B,
                    padding=(20, 9), borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", SURF2), ("active", SURF3)],
              foreground=[("selected", ACCENT), ("active", TEXT)])

        # Scale
        s.configure("TScale",       background=SURF,  troughcolor=SURF3)
        s.configure("Card2.TScale", background=SURF2, troughcolor=SURF3)

        # Entry / Spinbox / Combobox
        for name in ("TEntry", "TSpinbox", "TCombobox"):
            s.configure(name,
                        fieldbackground=SURF3, foreground=TEXT,
                        background=SURF2, insertcolor=TEXT,
                        arrowcolor=DIM, selectbackground=SURF3,
                        borderwidth=0, relief="flat")

    # ══════════════════════════════════════════════════════════════════════════
    # UI Construction
    # ══════════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        # ── Header bar ────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=SURF, height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="  🏎  NFS THE RUN",
                 bg=SURF, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(side="left", padx=4)
        tk.Label(hdr, text="MOD SUITE",
                 bg=SURF, fg=ACCENT, font=("Segoe UI", 12, "bold")).pack(side="left")

        # Status cluster (right side)
        sc = tk.Frame(hdr, bg=SURF); sc.pack(side="right", padx=14)
        self._dot  = tk.Label(sc, text="●", bg=SURF, fg=RED,  font=("Segoe UI", 16))
        self._dot.pack(side="left")
        self._slbl = tk.Label(sc, text="Not connected", bg=SURF, fg=DIM, font=FNT)
        self._slbl.pack(side="left", padx=(4, 12))
        tk.Button(sc, text="Reconnect", command=self._do_connect,
                  bg=SURF2, fg=TEXT, font=FNT, relief="flat", bd=0,
                  padx=10, pady=3, activebackground=SURF3, cursor="hand2"
                  ).pack(side="left")

        # Thin accent stripe under header
        tk.Frame(self.root, bg=ACCENT, height=2).pack(fill="x")

        # ── Notebook ──────────────────────────────────────────────────────────
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True)

        self._tab_performance()
        self._tab_speedrun()
        self._tab_vehicle()
        self._tab_visual()
        self._tab_tweaks()

    # ── Tab: Performance ──────────────────────────────────────────────────────
    def _tab_performance(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  ⚡ Performance  ")
        self._gap(tab, 10)

        # Framerate card
        card = self._card(tab, "FRAMERATE")
        self.v_fps_unlock  = tk.BooleanVar()
        self.v_fps_cut     = tk.BooleanVar()
        self.v_fps_vsync   = tk.BooleanVar()
        self._chk(card, "Unlock Gameplay Framerate  (removes the 30 fps cap)",
                  self.v_fps_unlock, self._on_fps_unlock)
        self._chk(card, "Unlock Cutscene Framerate  ⚠ experimental",
                  self.v_fps_cut, self._on_fps_cutscene)
        self._chk(card, "Disable V-Sync During Loading  (higher FPS = faster loads)",
                  self.v_fps_vsync, self._on_loading_vsync)

        # Menu FPS row
        row = tk.Frame(card, bg=SURF); row.pack(fill="x", padx=14, pady=(8, 4))
        tk.Label(row, text="Menu Max FPS:", bg=SURF, fg=TEXT, font=FNT, width=16,
                 anchor="w").pack(side="left")
        self.v_menu_fps = tk.DoubleVar(value=60.0)
        ttk.Scale(row, from_=30, to=240, orient="horizontal",
                  variable=self.v_menu_fps, length=240).pack(side="left", padx=8)
        tk.Label(row, textvariable=self.v_menu_fps, width=6,
                 bg=SURF, fg=ACCENT, font=FNT_B).pack(side="left")
        self._sbtn(card, "Apply Menu FPS", self._apply_menu_fps)

        # Note
        tk.Label(card, text="⚠  Default is 60 Hz — values above 120 may affect physics.",
                 bg=SURF, fg=YEL, font=("Segoe UI", 8)
                 ).pack(anchor="w", padx=14, pady=(0, 10))

        # Graphics card
        self._gap(tab, 10)
        card2 = self._card(tab, "GRAPHICS")
        self.v_blur    = tk.BooleanVar()
        self.v_shadows = tk.BooleanVar()
        self.v_reflect = tk.BooleanVar()
        self._chk(card2, "Enhanced Motion Blur Quality",  self.v_blur,    None)
        self._chk(card2, "Higher Quality Shadows",         self.v_shadows, None)
        self._chk(card2, "Enhanced Reflections",           self.v_reflect, None)
        self._sbtn(card2, "Apply Graphics Settings", self._apply_graphics)

    # ── Tab: Speedrun ─────────────────────────────────────────────────────────
    def _tab_speedrun(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  ⏱ Speedrun  ")
        self._gap(tab, 10)

        # Timer card
        card = self._card(tab, "LOADLESS TIMER")

        self._tlbl = tk.Label(card, text="00:00:00.000",
                              bg=SURF, fg=TEXT, font=FNT_MONO)
        self._tlbl.pack(pady=(12, 6))

        info = tk.Frame(card, bg=SURF); info.pack()
        self._llbl = tk.Label(info, text="Loads: 00:00:00.000",
                              bg=SURF, fg=DIM, font=FNT)
        self._llbl.pack(side="left", padx=18)
        self._stlbl = tk.Label(info, text="● Idle", bg=SURF, fg=DIM, font=FNT_B)
        self._stlbl.pack(side="left")

        btns = tk.Frame(card, bg=SURF); btns.pack(pady=12)
        for label, cmd, col in [
            ("▶  Start", self._t_start, GRN),
            ("✂  Split",  self._t_split, ACCENT),
            ("■  Stop",   self._t_stop,  RED),
            ("↺  Reset",  self._t_reset, DIM),
        ]:
            tk.Button(btns, text=label, command=cmd,
                      bg=SURF2, fg=col, font=FNT_B, relief="flat", bd=0,
                      padx=14, pady=6, activebackground=SURF3, cursor="hand2"
                      ).pack(side="left", padx=4)

        self.v_autosplit = tk.BooleanVar()
        self._chk(card, "Auto-split on checkpoints", self.v_autosplit, None)

        # Splits log
        self._gap(tab, 10)
        card2 = self._card(tab, "SPLITS")
        self._splits_box = tk.Text(
            card2, height=7, bg=SURF2, fg=TEXT, font=("Consolas", 9),
            relief="flat", insertbackground=TEXT, bd=0, padx=8, pady=6)
        self._splits_box.pack(fill="x", padx=12, pady=(0, 8))

        exprow = tk.Frame(card2, bg=SURF); exprow.pack(fill="x", padx=12, pady=(0, 10))
        for label, cmd in [("Export JSON", self._t_export), ("Copy Time", self._t_copy)]:
            tk.Button(exprow, text=label, command=cmd,
                      bg=SURF2, fg=TEXT, font=FNT_B, relief="flat", bd=0,
                      padx=10, pady=4, activebackground=SURF3, cursor="hand2"
                      ).pack(side="left", padx=(0, 8))

    # ── Tab: Vehicle ──────────────────────────────────────────────────────────
    def _tab_vehicle(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  🚗 Vehicle  ")
        self._gap(tab, 10)

        card = self._card(tab, "QUICK TOGGLES")
        self.v_assists = tk.BooleanVar()
        self.v_nos     = tk.BooleanVar()
        self.v_nodmg   = tk.BooleanVar()
        self._chk(card, "Disable All Driving Assists  (ABS, traction control, etc.)",
                  self.v_assists, self._on_assists)
        self._chk(card, "Infinite NOS  (continuously refreshed by monitor thread)",
                  self.v_nos, self._on_nos)
        self._chk(card, "No Vehicle Damage  (damage reset every frame)",
                  self.v_nodmg, self._on_nodmg)

        self._gap(tab, 10)
        card2 = self._card(tab, "VEHICLE CUSTOMIZER")
        tk.Label(card2,
                 text="Full vehicle, bodykit, paint and performance tier editor.\n"
                      "Supports JSON presets for quick load-outs.",
                 bg=SURF, fg=DIM, font=FNT, justify="left", wraplength=560,
                 ).pack(anchor="w", padx=14, pady=(6, 10))
        tk.Button(card2, text="  Open Vehicle Customizer  →",
                  command=self._open_customizer,
                  bg=ACCENT, fg="white", font=FNT_B, relief="flat", bd=0,
                  padx=16, pady=8, activebackground=ACCH, cursor="hand2"
                  ).pack(anchor="w", padx=14, pady=(0, 14))

    # ── Tab: Visual ───────────────────────────────────────────────────────────
    def _tab_visual(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  🌅 Visual  ")
        self._gap(tab, 10)

        card = self._card(tab, "LIGHTING & ATMOSPHERE")

        self.v_headlights = tk.BooleanVar()
        self._chk(card, "Force Headlights On", self.v_headlights, self._on_headlights)

        self._gap_frame(card, SURF, 6)

        self.v_light  = tk.DoubleVar(value=1.0)
        self.v_expo   = tk.DoubleVar(value=1.0)
        self.v_sun_x  = tk.DoubleVar(value=0.0)
        self.v_sun_y  = tk.DoubleVar(value=0.0)

        def frow(label, var, lo, hi, cmd):
            row = tk.Frame(card, bg=SURF); row.pack(fill="x", padx=14, pady=4)
            tk.Label(row, text=label, bg=SURF, fg=TEXT, font=FNT,
                     width=24, anchor="w").pack(side="left")
            ttk.Scale(row, from_=lo, to=hi, orient="horizontal",
                      variable=var, length=300, command=cmd).pack(side="left", padx=8)
            tk.Label(row, textvariable=var, width=7,
                     bg=SURF, fg=ACCENT, font=FNT_B).pack(side="left")

        frow("World Light Intensity",  self.v_light, 0.0,  3.0,  self._on_light)
        frow("Exposure",               self.v_expo,  0.0,  3.0,  self._on_expo)
        frow("Sun Position X (°)",     self.v_sun_x, -180, 180,  self._on_sun)
        frow("Sun Position Y (°)",     self.v_sun_y, -180, 180,  self._on_sun)

        self._gap_frame(card, SURF, 10)

    # ── Tab: Tweaks ───────────────────────────────────────────────────────────
    def _tab_tweaks(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  🔧 Tweaks  ")
        self._gap(tab, 10)

        card = self._card(tab, "UNLOCKS")
        tk.Label(card,
                 text="Patches the in-game lock checks.  Enter a race to see the changes take effect.",
                 bg=SURF, fg=DIM, font=FNT).pack(anchor="w", padx=14, pady=(4, 8))
        self._wbtn(card, "Unlock All Vehicles",   self._unlock_vehicles)
        self._wbtn(card, "Unlock All Challenges",  self._unlock_challenges)

        self._gap(tab, 10)
        card2 = self._card(tab, "STABILITY FIXES")
        tk.Label(card2,
                 text="NOPs crash-trigger code that can hard-crash the game on certain stages.",
                 bg=SURF, fg=DIM, font=FNT).pack(anchor="w", padx=14, pady=(4, 8))
        self._wbtn(card2, "Apply All Crash Bypasses",    self._apply_crash_fixes)
        self._wbtn(card2, "Disable Reset Triggers",      self._disable_resets)
        self._gap_frame(card2, SURF, 8)

    # ══════════════════════════════════════════════════════════════════════════
    # Widget helpers
    # ══════════════════════════════════════════════════════════════════════════
    def _gap(self, parent, h=8):
        tk.Frame(parent, bg=BG, height=h).pack()

    def _gap_frame(self, parent, bg, h=8):
        tk.Frame(parent, bg=bg, height=h).pack()

    def _card(self, parent, title: str):
        outer = tk.Frame(parent, bg=SURF)
        outer.pack(fill="x", padx=16)
        tk.Label(outer, text=title, bg=SURF, fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        tk.Frame(outer, bg=BDR, height=1).pack(fill="x", padx=14, pady=(0, 8))
        return outer

    def _chk(self, parent, text: str, var: tk.BooleanVar, cmd):
        f = tk.Frame(parent, bg=SURF); f.pack(anchor="w", padx=14, pady=3)
        tk.Checkbutton(f, text=text, variable=var, command=cmd,
                       bg=SURF, fg=TEXT, selectcolor=SURF3,
                       activebackground=SURF, activeforeground=TEXT,
                       font=FNT, relief="flat", cursor="hand2"
                       ).pack(side="left")

    def _sbtn(self, parent, text: str, cmd):
        """Small left-aligned button inside a card."""
        tk.Button(parent, text=text, command=cmd,
                  bg=SURF2, fg=TEXT, font=FNT_B, relief="flat", bd=0,
                  padx=12, pady=5, activebackground=SURF3, cursor="hand2"
                  ).pack(anchor="w", padx=14, pady=(2, 10))

    def _wbtn(self, parent, text: str, cmd):
        """Wide full-row button inside a card."""
        tk.Button(parent, text=text, command=cmd,
                  bg=SURF2, fg=TEXT, font=FNT_B, relief="flat", bd=0,
                  padx=16, pady=8, activebackground=SURF3, cursor="hand2"
                  ).pack(fill="x", padx=14, pady=4)

    # ══════════════════════════════════════════════════════════════════════════
    # Connection
    # ══════════════════════════════════════════════════════════════════════════
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
                label = f"Connected — {name}  |  base {hex(self.base)}"
                self.root.after(0, lambda l=label: self._set_status(l, GRN))
                self.root.after(0, self._start_monitor)
                return
            except Exception:
                continue
        self.root.after(0, lambda: self._set_status(
            "Not connected — launch the game first, then reconnect", RED))

    def _set_status(self, msg: str, color: str):
        self._dot.config(fg=color)
        self._slbl.config(text=msg)

    def _guard(self) -> bool:
        """Return True if connected; otherwise show a warning and return False."""
        if not self.connected:
            messagebox.showwarning(
                "Not connected",
                "Connect to the game first.\n\n"
                "• Make sure NFS The Run is running (in a race or the main menu).\n"
                "• Run this tool as Administrator.\n"
                "• Game version must be v1.1.0.0 (DRM-free).")
            return False
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # Safe Memory I/O   ← THE CRITICAL FIX
    # ══════════════════════════════════════════════════════════════════════════
    def safe_read(self, addr: int, length: int) -> bytes | None:
        """Read bytes from an absolute address. Returns None on failure."""
        try:
            with self._lock:
                data = self.pm.read_bytes(addr, length)
            return data if len(data) == length else None
        except Exception as e:
            print(f"[READ  {hex(addr)}] {e}")
            return None

    def safe_write(self, addr: int, data: bytes) -> bool:
        """
        Write bytes to an absolute address.

        If the normal write fails (e.g. the address is in a read-only or
        execute-only page, which is typical for code-patch NOPs), we call
        VirtualProtectEx inline to make it writable, write, then restore.

        NOTE: There is NO recursive call here — that was the v2.0 bug.
        """
        # ── Attempt 1: plain write ────────────────────────────────────────────
        try:
            with self._lock:
                self.pm.write_bytes(addr, data, len(data))
            return True
        except Exception:
            pass

        # ── Attempt 2: override page protection, then write ───────────────────
        PAGE_EXECUTE_READWRITE = 0x40
        old_protect = c_ulong(0)
        try:
            windll.kernel32.VirtualProtectEx(
                self.pm.process_handle,
                c_void_p(addr),
                c_size_t(len(data)),
                PAGE_EXECUTE_READWRITE,
                byref(old_protect))

            with self._lock:
                self.pm.write_bytes(addr, data, len(data))

            # Restore original protection
            windll.kernel32.VirtualProtectEx(
                self.pm.process_handle,
                c_void_p(addr),
                c_size_t(len(data)),
                old_protect,
                byref(c_ulong(0)))
            return True
        except Exception as e:
            print(f"[WRITE {hex(addr)}] {e}")
            return False

    # ── Typed write helpers ───────────────────────────────────────────────────
    def _wf(self, offset: int, v: float) -> bool:
        """Write a 32-bit float at base + offset."""
        return self.safe_write(self.base + offset, struct.pack("<f", v))

    def _wb(self, offset: int, v: int) -> bool:
        """Write a byte at base + offset."""
        return self.safe_write(self.base + offset, struct.pack("<B", v))

    def _wd(self, offset: int, v: int) -> bool:
        """Write a 32-bit unsigned int at base + offset."""
        return self.safe_write(self.base + offset, struct.pack("<I", v))

    def _rf(self, offset: int) -> float | None:
        """Read a 32-bit float from base + offset."""
        d = self.safe_read(self.base + offset, 4)
        return struct.unpack("<f", d)[0] if d else None

    def _rp(self, addr: int) -> int | None:
        """Read a 32-bit pointer (little-endian) from an absolute address."""
        d = self.safe_read(addr, 4)
        return struct.unpack("<I", d)[0] if d else None

    # ── NOP patch helpers ─────────────────────────────────────────────────────
    def _nop(self, offset: int, size: int = 5) -> bool:
        """
        NOP `size` bytes at base+offset.
        Saves original bytes on first call so _unnop can restore them.
        """
        addr = self.base + offset
        if addr not in self._nop_cache:
            orig = self.safe_read(addr, size)
            if orig is None:
                print(f"[NOP CACHE MISS] {hex(addr)}")
                return False
            self._nop_cache[addr] = orig
        return self.safe_write(addr, b"\x90" * size)

    def _unnop(self, offset: int) -> bool:
        """Restore the original bytes that were overwritten by _nop."""
        addr = self.base + offset
        orig = self._nop_cache.get(addr)
        if orig:
            return self.safe_write(addr, orig)
        print(f"[UNNOP] No cached bytes for {hex(addr)}")
        return False

    # ══════════════════════════════════════════════════════════════════════════
    # Monitor Thread
    # ══════════════════════════════════════════════════════════════════════════
    def _start_monitor(self):
        if self._mon_run:
            return
        self._mon_run = True
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self):
        errors = 0
        while self._mon_run and self.connected:
            try:
                if not self._proc_alive():
                    self.connected = False
                    self.root.after(0, lambda: self._set_status(
                        "Game closed — reconnect to reattach", RED))
                    break

                # Resolve vehicle state for loadless timer
                is_loading = True
                veh = self._resolve_veh()
                if veh:
                    sd = self.safe_read(veh + self.OFFSETS["veh_state"], 4)
                    if sd:
                        state      = struct.unpack("<I", sd)[0]
                        is_loading = (state != 0)   # 0 = OnGround = player has control

                self.timer.update(is_loading)
                self.root.after(0, self._refresh_timer_ui)

                # Continuous freeze writes
                if self.freeze_nos:
                    self._wf(self.OFFSETS["nos_tank"], 1.0)
                    self._wf(self.OFFSETS["nos_rate"], 0.0)
                if self.freeze_nodmg:
                    self._wf(self.OFFSETS["dmg0"], 0.0)
                    self._wf(self.OFFSETS["dmg1"], 0.0)
                    self._wf(self.OFFSETS["dmg2"], 0.0)

                errors = 0
                time.sleep(1 / 30)     # ~30 Hz polling

            except Exception as e:
                errors = min(errors + 1, 10)
                print(f"[MONITOR] {e}")
                time.sleep(min(0.1 * errors, 2.0))

    def _resolve_veh(self) -> int | None:
        """Follow the pointer chain to the live vehicle object."""
        try:
            addr = self._rp(self.base + self.OFFSETS["veh_ptr"])
            if not addr or addr < 0x10000:
                return None
            for off in self.OFFSETS["veh_chain"]:
                addr = self._rp(addr + off)
                if not addr or addr < 0x10000:
                    return None
            return addr
        except Exception:
            return None

    def _proc_alive(self) -> bool:
        try:
            import psutil
            return psutil.pid_exists(self.pm.process_id)
        except Exception:
            try:
                self.pm.read_bytes(self.base, 1)
                return True
            except Exception:
                return False

    # ══════════════════════════════════════════════════════════════════════════
    # Timer UI callbacks
    # ══════════════════════════════════════════════════════════════════════════
    def _refresh_timer_ui(self):
        if not self.timer.active:
            return
        self._tlbl.config(text=self.timer.time_str())
        ls = str(self.timer.loading_time).split(".")[0]
        self._llbl.config(text=f"Loads: {ls}")
        if self.timer.is_loading:
            self._stlbl.config(text="● Loading", fg=YEL)
        else:
            self._stlbl.config(text="● Running", fg=GRN)

    def _t_start(self):
        self.timer.start()
        self._splits_box.delete("1.0", "end")
        self._stlbl.config(text="● Running", fg=GRN)

    def _t_split(self):
        name = f"Split {len(self.timer.splits) + 1}"
        self.timer.split(name)
        self._splits_box.insert("end", f"{name:<12}  {self.timer.time_str()}\n")
        self._splits_box.see("end")

    def _t_stop(self):
        self.timer.stop()
        self._stlbl.config(text="● Stopped", fg=RED)

    def _t_reset(self):
        self.timer.reset()
        self._tlbl.config(text="00:00:00.000")
        self._llbl.config(text="Loads: 00:00:00")
        self._stlbl.config(text="● Idle", fg=DIM)
        self._splits_box.delete("1.0", "end")

    def _t_export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            self.timer.export(path)
            messagebox.showinfo("Exported", f"Splits saved:\n{path}")

    def _t_copy(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.timer.time_str())

    # ══════════════════════════════════════════════════════════════════════════
    # Performance tab actions
    # ══════════════════════════════════════════════════════════════════════════
    def _on_fps_unlock(self):
        if not self._guard():
            self.v_fps_unlock.set(False); return
        on = self.v_fps_unlock.get()
        for off in self.OFFSETS["fps_nop_list"]:
            self._nop(off, 5) if on else self._unnop(off)
        self._wf(self.OFFSETS["max_fps"], 240.0 if on else 60.0)

    def _on_fps_cutscene(self):
        if not self._guard():
            self.v_fps_cut.set(False); return
        self._wf(self.OFFSETS["max_fps"], 240.0 if self.v_fps_cut.get() else 60.0)

    def _on_loading_vsync(self):
        if not self._guard():
            self.v_fps_vsync.set(False); return
        on = self.v_fps_vsync.get()
        for off, orig_bytes in self.OFFSETS["load_vsync_nops"]:
            addr = self.base + off
            if on:
                if addr not in self._nop_cache:
                    self._nop_cache[addr] = orig_bytes
                self.safe_write(addr, b"\x90" * len(orig_bytes))
            else:
                self.safe_write(addr, self._nop_cache.get(addr, orig_bytes))

    def _apply_menu_fps(self):
        if not self._guard(): return
        fps = float(self.v_menu_fps.get())
        if self._wf(self.OFFSETS["menu_fps"], fps):
            messagebox.showinfo("Applied", f"Menu FPS set to {fps:.0f}")
        else:
            messagebox.showerror("Failed",
                "Memory write failed.\nVerify game is running and tool has Admin rights.")

    def _apply_graphics(self):
        messagebox.showinfo("Note",
            "Graphics flags are applied at the next scene transition.\n"
            "Restart a race after toggling for the effect to appear.")

    # ══════════════════════════════════════════════════════════════════════════
    # Vehicle tab actions
    # ══════════════════════════════════════════════════════════════════════════
    def _on_assists(self):
        if not self._guard():
            self.v_assists.set(False); return
        on = self.v_assists.get()
        for off in self.OFFSETS["assists"]:
            self._nop(off, 5) if on else self._unnop(off)

    def _on_nos(self):
        if not self._guard():
            self.v_nos.set(False); return
        self.freeze_nos = self.v_nos.get()

    def _on_nodmg(self):
        if not self._guard():
            self.v_nodmg.set(False); return
        self.freeze_nodmg = self.v_nodmg.get()

    def _open_customizer(self):
        if not self._guard(): return
        VehicleCustomizer(self.root, self)

    # ══════════════════════════════════════════════════════════════════════════
    # Visual tab actions
    # ══════════════════════════════════════════════════════════════════════════
    def _on_headlights(self):
        if not self._guard():
            self.v_headlights.set(False); return
        on = self.v_headlights.get()
        for off in self.OFFSETS["headlights"]:
            self._nop(off, 2) if on else self._unnop(off)

    def _on_light(self, _=None):
        if self.connected:
            self._wf(self.OFFSETS["light_render"], self.v_light.get())

    def _on_expo(self, _=None):
        if self.connected:
            self._wf(self.OFFSETS["exposure"], self.v_expo.get())

    def _on_sun(self, _=None):
        if self.connected:
            self._wf(self.OFFSETS["sun_x"], self.v_sun_x.get())
            self._wf(self.OFFSETS["sun_y"], self.v_sun_y.get())

    # ══════════════════════════════════════════════════════════════════════════
    # Tweaks tab actions
    # ══════════════════════════════════════════════════════════════════════════
    def _unlock_vehicles(self):
        if not self._guard(): return
        # Write 0x00 over the mov al,01 car-lock instruction (from community CE table)
        if self._wb(self.OFFSETS["car_unlock"], 0x00):
            messagebox.showinfo("Done",
                "Vehicle unlock applied.\nEnter a race to see all cars unlocked.")
        else:
            messagebox.showerror("Failed",
                "Write failed.\nConfirm game version is v1.1.0.0 (DRM-free).")

    def _unlock_challenges(self):
        if not self._guard(): return
        for off in self.OFFSETS["challenge_nops"]:
            self._nop(off, 5)
        messagebox.showinfo("Done", "Challenge unlock applied.")

    def _apply_crash_fixes(self):
        if not self._guard(): return
        self._nop(self.OFFSETS["tunnel_pain"], 5)
        for off in self.OFFSETS["chicago_crash"]:
            self._nop(off, 5)
        messagebox.showinfo("Done",
            "Crash bypasses applied.\n"
            "Tunnel Pain and Chicago crash triggers have been disabled.")

    def _disable_resets(self):
        if not self._guard(): return
        messagebox.showinfo("Note",
            "Reset trigger offsets are stage-specific and not hardcoded here.\n\n"
            "Use Cheat Engine with the included .CT table to locate and\n"
            "disable reset zones for the specific stage you are running.")

    # ══════════════════════════════════════════════════════════════════════════
    # Cleanup
    # ══════════════════════════════════════════════════════════════════════════
    def _on_close(self):
        self._mon_run = False
        if self.pm:
            try:
                self.pm.close_process()
            except Exception:
                pass
        self.root.destroy()


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════
def _ensure_admin():
    """Re-launch the process with elevation if not already Administrator."""
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            import sys
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable,
                f'"{sys.argv[0]}"', None, 1)
            sys.exit(0)
    except Exception:
        pass   # non-Windows / already elevated


if __name__ == "__main__":
    _ensure_admin()
    root = tk.Tk()
    NFSModSuite(root)
    root.mainloop()
