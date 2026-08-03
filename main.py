#!/usr/bin/env python3
from __future__ import annotations

import ctypes
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _emergency_crash_log(exc: BaseException):
    try:
        appdata = os.environ.get("APPDATA")
        if os.name == "nt" and appdata:
            base = appdata
        else:
            base = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
        path = os.path.join(base, "nfstr_data", "startup_crash.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=f)
        return path
    except Exception:
        return None


def main():
    if os.name != "nt":
        print("This tool reads/writes Windows process memory and only runs on Windows.")
        sys.exit(1)

    if not _is_admin():
        print("Warning: not running as Administrator. Attaching to the game may fail")
        print("depending on how it was launched. If 'Attach' fails in the GUI, close")
        print("this and re-launch from an elevated (Run as administrator) terminal.\n")

    from gui.app import main as gui_main
    gui_main()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        crash_path = _emergency_crash_log(e)
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "NFS: The Run Mod Menu -- startup error",
                "The mod menu hit an unexpected error on startup.\n\n"
                f"{type(e).__name__}: {e}\n\n"
                + (f"Details were written to:\n{crash_path}" if crash_path
                    else "Run from a terminal to see the full error.")
            )
        except Exception:
            pass
        raise
