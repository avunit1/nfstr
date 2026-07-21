"""
gui/app.py
Tkinter front-end. Deliberately data-driven: every checkbox/slider you
see is generated from data/signatures.json plus a small CATEGORY_ORDER
list below, rather than hand-built per feature -- adding a new signature
to the JSON (via tools/build_signatures.py) makes it show up here with
no GUI code changes needed.

Layout
------
  [ status bar: process state | Attach | Calibrate ]
  [ tabs: Performance | Crash Fixes | Timers | Assists | Vehicle | ... ]
    each tab: one row per signature
      - toggle patch_types (nop/byte_write/jcc_invert/jcc_force_jmp/
        codecave/cave_field_freeze) -> a checkbox, optionally with a
        value entry box next to it for adjustable codecaves
      - pointer_write -> a one-shot "Apply" row (not a persistent toggle)
  [ vehicle swap panel: search box + list, backed by data/vehicles.json ]
  [ log panel ]
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import process, paths
from core.memory import SafeMemory
from core.codecave import CodeCaveEngine
from core.cache import BuildCache
from core.resolver import SignatureResolver
from core import logging_setup
from features.engine import FeatureEngine

SIGNATURES_PATH = paths.bundled_resource("data", "signatures.json")
VEHICLES_PATH = paths.bundled_resource("data", "vehicles.json")
CACHE_PATH = paths.cache_path()

log = logging.getLogger("nfstr.gui")

CATEGORY_ORDER = [
    "Performance", "Crash Fixes", "Timers", "Assists", "Vehicle",
    "Game", "AI / Race Setup", "Traffic", "World", "UI", "Debug / UI",
]

RISK_COLOR = {"low": "#2e7d32", "medium": "#e65100", "high": "#c62828"}
AUTO_ATTACH_POLL_MS = 2000


class ModMenuApp:
    # Signatures with their own purpose-built tab/controls rather than a
    # generic checkbox row -- excluded from the plain category listing so
    # there's exactly one, correctly-guarded way to trigger them.
    DEDICATED_TAB_IDS = {"vehicle_swap_car_object"}

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("NFS: The Run -- Mod Menu")
        self.root.geometry("900x680")

        self.log_file_path = logging_setup.setup_logging(verbose=False)
        log.info("GUI starting. Bundled resources at: %s", paths.bundled_resource())
        log.info("Writable data/cache dir: %s", paths.writable_dir())

        self.signatures = json.load(open(SIGNATURES_PATH, encoding="utf-8"))
        self.by_id = {s["id"]: s for s in self.signatures}
        self.vehicles = json.load(open(VEHICLES_PATH, encoding="utf-8"))
        log.info("Loaded %d signatures, %d vehicles", len(self.signatures), len(self.vehicles))

        self.target = None
        self.resolver = None
        self.mem = None
        self.cave = None
        self.engine = None
        self._attaching = False

        self.checkbox_vars: dict[str, tk.BooleanVar] = {}
        self.value_vars: dict[str, tk.StringVar] = {}
        self.auto_attach_var = tk.BooleanVar(value=True)
        self.verbose_var = tk.BooleanVar(value=False)

        self._build_layout()
        self._try_attach(initial=True)
        self.root.after(300, self._drain_log_queue)
        self.root.after(AUTO_ATTACH_POLL_MS, self._auto_attach_poll)

    # ------------------------------------------------------------------ #
    def _build_layout(self):
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill="x")

        self.status_label = ttk.Label(top, text="Not attached", foreground="#c62828")
        self.status_label.pack(side="left")

        ttk.Button(top, text="Attach / Re-attach", command=self._try_attach).pack(side="right", padx=2)
        ttk.Button(top, text="Re-run calibration", command=self._recalibrate).pack(side="right", padx=2)
        ttk.Checkbutton(top, text="Auto-attach when game launches",
                          variable=self.auto_attach_var).pack(side="right", padx=8)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=4)

        self.tab_frames: dict[str, ttk.Frame] = {}
        present_categories = [c for c in CATEGORY_ORDER
                                if any(s.get("category") == c and not s.get("internal") for s in self.signatures)]
        for cat in present_categories:
            frame = ttk.Frame(self.notebook, padding=8)
            self.notebook.add(frame, text=cat)
            self.tab_frames[cat] = frame
            self._build_category_tab(frame, cat)

        self._build_vehicle_tab()
        self._build_log_tab()

    def _build_log_tab(self):
        frame = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(frame, text="Log")

        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        ttk.Checkbutton(bar, text="Verbose (debug) logging", variable=self.verbose_var,
                          command=self._on_verbose_toggle).pack(side="left")
        ttk.Button(bar, text="Copy all to clipboard", command=self._copy_log).pack(side="right", padx=2)
        ttk.Button(bar, text="Save to file...", command=self._save_log).pack(side="right", padx=2)
        ttk.Button(bar, text="Open logs folder", command=self._open_logs_folder).pack(side="right", padx=2)
        ttk.Button(bar, text="Clear view", command=self._clear_log_view).pack(side="right", padx=2)

        ttk.Label(frame, foreground="#757575",
                   text=f"Full session log is always written to: {self.log_file_path}"
                   ).pack(anchor="w", pady=(4, 4))

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(text_frame, state="disabled", wrap="word", font=("Consolas", 9))
        ls = ttk.Scrollbar(text_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=ls.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        ls.pack(side="right", fill="y")

    def _on_verbose_toggle(self):
        logging_setup.setup_logging(verbose=self.verbose_var.get())
        log.info("Verbose logging %s", "enabled" if self.verbose_var.get() else "disabled")

    def _append_log_lines(self, lines: list[str]):
        if not lines:
            return
        self.log_text.configure(state="normal")
        for line in lines:
            self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _drain_log_queue(self):
        self._append_log_lines(logging_setup.drain_queue())
        self.root.after(300, self._drain_log_queue)

    def _copy_log(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_text.get("1.0", "end"))
        messagebox.showinfo("Copied", "Log copied to clipboard.")

    def _save_log(self):
        from tkinter import filedialog
        target = filedialog.asksaveasfilename(defaultextension=".log",
                                                 initialfile="nfstr_modmenu_log.txt")
        if target:
            with open(target, "w", encoding="utf-8") as f:
                f.write(self.log_text.get("1.0", "end"))
            messagebox.showinfo("Saved", f"Log saved to {target}")

    def _open_logs_folder(self):
        folder = paths.logs_dir()
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except Exception:
            self._log(f"Logs folder: {folder}")

    def _clear_log_view(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _auto_attach_poll(self):
        try:
            if self.auto_attach_var.get():
                if self.target is None and not self._attaching:
                    if process.is_game_running():
                        log.info("Auto-attach: game process detected, attaching...")
                        self._try_attach(initial=True, silent=True)
                elif self.target is not None:
                    if not process.is_process_alive(self.target):
                        log.warning("Attached process appears to have exited.")
                        self._on_process_lost()
        except Exception:
            log.exception("Error in auto-attach poll loop")
        finally:
            self.root.after(AUTO_ATTACH_POLL_MS, self._auto_attach_poll)

    def _on_process_lost(self):
        if self.engine:
            self.engine.shutdown()
        self.target = self.resolver = self.mem = self.cave = self.engine = None
        self.status_label.configure(text="Game process exited -- not attached", foreground="#c62828")
        for sid, var in self.checkbox_vars.items():
            var.set(False)

    def _build_category_tab(self, frame: ttk.Frame, category: str):
        entries = [s for s in self.signatures if s.get("category") == category and not s.get("internal")
                    and s["id"] not in self.DEDICATED_TAB_IDS]
        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for row, sig in enumerate(entries):
            self._build_signature_row(inner, sig, row)

    def _build_signature_row(self, parent, sig: dict, row: int):
        sid = sig["id"]
        patch_type = sig["patch_type"]

        risk = sig.get("risk", "medium")
        dot = tk.Label(parent, text="\u25CF", fg=RISK_COLOR.get(risk, "#616161"))
        dot.grid(row=row, column=0, sticky="w", padx=(0, 4), pady=3)

        if patch_type == "pointer_write":
            ttk.Label(parent, text=sig["label"], width=42, anchor="w").grid(row=row, column=1, sticky="w")
            sv = tk.StringVar(value="0")
            self.value_vars[sid] = sv
            ttk.Entry(parent, textvariable=sv, width=8).grid(row=row, column=2, padx=4)
            ttk.Button(parent, text="Apply", width=8,
                        command=lambda s=sig: self._apply_one_shot(s)).grid(row=row, column=3, padx=4)
        else:
            var = tk.BooleanVar(value=False)
            self.checkbox_vars[sid] = var
            cb = ttk.Checkbutton(parent, text=sig["label"], variable=var,
                                   command=lambda s=sig, v=var: self._on_toggle(s, v))
            cb.grid(row=row, column=1, sticky="w", pady=3)

            if sig.get("value_offset") is not None or patch_type == "cave_field_freeze":
                default = self._default_value_for(sig)
                sv = tk.StringVar(value=str(default))
                self.value_vars[sid] = sv
                ttk.Entry(parent, textvariable=sv, width=8).grid(row=row, column=2, padx=4)

        # tooltip-ish: description shown as a smaller grey line underneath on hover
        # (kept simple -- a Label bound to <Enter>/<Leave> would need extra state;
        # instead we just show it inline, muted, to the right)
        note = sig.get("desc", "")
        if note:
            ttk.Label(parent, text=note, foreground="#757575", wraplength=380,
                       justify="left").grid(row=row, column=4, sticky="w", padx=(10, 0))

    @staticmethod
    def _default_value_for(sig: dict):
        vt = sig.get("value_type")
        defaults = {
            "traffic_density_scale": 0.05, "traffic_max_density": 0.15,
            "traffic_vehicle_limit": 25, "ai_difficulty_expert": 3,
            "ai_number_of_players": 8, "ai_player_grid_position": 1,
            "game_difficulty_scalar": 5.0, "game_glue_scalar": 0.7,
            "vehicle_damage_threshold": 101, "tod_career_challenge": 4,
            "tod_multiplayer": 0, "perf_unlock_framerate": 60.0,
        }
        return defaults.get(sig["id"], 1.0 if vt == "float" else 1)

    def _build_vehicle_tab(self):
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="Vehicle Swap")

        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="Search:").pack(side="left")
        self.vehicle_search = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.vehicle_search, width=40)
        entry.pack(side="left", padx=6)
        entry.bind("<KeyRelease>", lambda e: self._refresh_vehicle_list())

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="both", expand=True, pady=6)
        self.vehicle_listbox = tk.Listbox(list_frame)
        vs = ttk.Scrollbar(list_frame, orient="vertical", command=self.vehicle_listbox.yview)
        self.vehicle_listbox.configure(yscrollcommand=vs.set)
        self.vehicle_listbox.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

        ttk.Button(frame, text="Swap to selected car (must be in a race/garage)",
                    command=self._swap_selected_vehicle).pack(pady=4)
        ttk.Label(frame, foreground="#757575", wraplength=800, justify="left",
                   text="Writes the vehicle's hash ID through the Car Object pointer chain. "
                        "Source note: works in single-player Challenge Series/story events; "
                        "does not work in multiplayer.").pack()

        self._vehicle_display = []
        self._refresh_vehicle_list()

    def _refresh_vehicle_list(self):
        query = self.vehicle_search.get().strip().lower()
        self.vehicle_listbox.delete(0, "end")
        self._vehicle_display = [v for v in self.vehicles if query in v["vehicle"].lower()] if query else self.vehicles
        for v in self._vehicle_display[:500]:  # cap for UI responsiveness
            self.vehicle_listbox.insert("end", f"{v['vehicle']}  [{v['entry']}]")

    def _swap_selected_vehicle(self):
        sel = self.vehicle_listbox.curselection()
        if not sel or not self.engine:
            return
        v = self._vehicle_display[sel[0]]
        sig = self.by_id["vehicle_swap_car_object"]
        ok = self.engine.enable(sig, value=v["hash_u32"], value_type="u32")
        self._log(f"Swap to {v['vehicle']} -> {'OK' if ok else 'FAILED'}")

    # ------------------------------------------------------------------ #
    def _log(self, msg: str):
        log.info(msg)

    def _try_attach(self, initial: bool = False, silent: bool = False):
        self._attaching = True
        try:
            try:
                self.target = process.attach(timeout=0)
            except ProcessLookupError as e:
                self.status_label.configure(text=f"Not running -- {e}", foreground="#c62828")
                if not initial and not silent:
                    messagebox.showwarning("Not found", str(e))
                return

            self.mem = SafeMemory(self.target.pm)
            self.cave = CodeCaveEngine(self.target.pm.process_handle, self.mem)
            cache = BuildCache(CACHE_PATH)
            self.resolver = SignatureResolver(self.target, self.signatures, cache)
            self.engine = FeatureEngine(self.resolver, self.mem, self.cave,
                                          all_signatures=self.by_id, log=self._log)

            self.status_label.configure(
                text=f"Attached: PID {self.target.pid} ({self.target.process_name}) "
                      f"base={hex(self.target.base)} sha256={(self.target.sha256 or 'unknown')[:12]}...",
                foreground="#2e7d32")
            self._recalibrate()
        except Exception:
            log.exception("Attach failed with an unexpected error")
            if not silent:
                messagebox.showerror("Attach failed",
                                       "Something went wrong attaching to the game. "
                                       "See the Log tab for details.")
        finally:
            self._attaching = False

    def _recalibrate(self):
        if not self.target:
            messagebox.showinfo("Not attached", "Attach to the game first.")
            return

        def work():
            n = len(self.resolver.sigs)
            def progress(i, total, sid, result):
                pass  # per-signature detail already goes to the log via resolver's own logger
            try:
                self.resolver.resolve_all(progress_cb=progress)
                ok = sum(1 for r in self.resolver.resolved.values() if r.verified)
                log.info("Calibration done: %d/%d signatures verified.", ok, n)
                if ok < n:
                    missing = [sid for sid, r in self.resolver.resolved.items() if not r.verified]
                    log.warning("Not verified (%d): %s", len(missing), ", ".join(missing))
            except Exception:
                log.exception("Calibration failed with an unexpected error")

        threading.Thread(target=work, daemon=True).start()

    def _on_toggle(self, sig: dict, var: tk.BooleanVar):
        if not self.engine:
            var.set(False)
            messagebox.showinfo("Not attached", "Attach to the game first.")
            return
        on = var.get()
        kwargs = {}
        sid = sig["id"]
        if sid in self.value_vars:
            raw = self.value_vars[sid].get()
            try:
                value = float(raw) if sig.get("value_type") == "float" else int(float(raw))
            except ValueError:
                value = self._default_value_for(sig)
            kwargs["value"] = value
            if sig["patch_type"] in ("pointer_write", "freeze"):
                kwargs["value_type"] = sig.get("value_type", "u32")

        try:
            ok = self.engine.toggle(sig, on, **kwargs)
        except Exception:
            log.exception("Unexpected error toggling %s", sid)
            ok = False
        if not ok:
            var.set(not on)  # snap back so the checkbox reflects reality
            messagebox.showwarning("Failed", f"Could not toggle '{sig['label']}'. See the Log tab for details.")

    def _apply_one_shot(self, sig: dict):
        if not self.engine:
            messagebox.showinfo("Not attached", "Attach to the game first.")
            return
        sid = sig["id"]
        kwargs = {}
        if sid in self.value_vars:
            raw = self.value_vars[sid].get()
            try:
                kwargs["value"] = int(float(raw))
            except ValueError:
                kwargs["value"] = 0
            kwargs["value_type"] = sig.get("value_type", "u32")
        try:
            ok = self.engine.enable(sig, **kwargs)
        except Exception:
            log.exception("Unexpected error applying %s", sid)
            ok = False
        log.info("%s -> %s", sig['label'], 'OK' if ok else 'FAILED')

    def on_close(self):
        log.info("Shutting down...")
        try:
            if self.engine:
                self.engine.shutdown()
        except Exception:
            log.exception("Error during shutdown")
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        app = ModMenuApp(root)
    except Exception:
        logging.getLogger("nfstr.gui").exception("Fatal error during startup")
        raise
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
