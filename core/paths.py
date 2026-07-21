"""
core/paths.py
Path resolution that works identically whether this is run from source
(`python main.py`) or as a PyInstaller --onefile exe.

PyInstaller's --onefile mode extracts bundled data to a temporary
directory (sys._MEIPASS) that's read-only in practice and deleted when
the process exits -- fine for the *static* data files we ship
(data/signatures.json, data/vehicles.json), but useless for anything we
need to persist between runs (the build cache, log files). Those go
next to the exe itself instead, so the whole tool stays a single
portable file plus a small sibling folder it manages itself.
"""

from __future__ import annotations

import os
import sys

FROZEN = getattr(sys, "frozen", False)


def app_root() -> str:
    """Directory containing main.py (source) or the .exe (frozen)."""
    if FROZEN:
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bundled_resource(*parts: str) -> str:
    """Path to a *read-only* bundled resource (e.g. data/signatures.json).
    Uses sys._MEIPASS when frozen, since that's where PyInstaller
    actually put the files packed in via --add-data."""
    base = sys._MEIPASS if FROZEN else app_root()  # type: ignore[attr-defined]
    return os.path.join(base, *parts)


def writable_dir() -> str:
    """Directory for anything we write at run time (cache, logs).
    Always lives next to the exe/main.py, never inside the frozen temp
    extraction folder."""
    d = os.path.join(app_root(), "nfstr_data")
    os.makedirs(d, exist_ok=True)
    return d


def cache_path() -> str:
    return os.path.join(writable_dir(), "build_cache.json")


def logs_dir() -> str:
    d = os.path.join(writable_dir(), "logs")
    os.makedirs(d, exist_ok=True)
    return d
