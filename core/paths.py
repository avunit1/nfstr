from __future__ import annotations

import os
import sys

FROZEN = getattr(sys, "frozen", False)


def app_root() -> str:
    if FROZEN:
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bundled_resource(*parts: str) -> str:
    base = sys._MEIPASS if FROZEN else app_root()
    return os.path.join(base, *parts)


def writable_dir() -> str:
    appdata = os.environ.get("APPDATA")
    if os.name == "nt" and appdata:
        base = appdata
    else:
        base = app_root()
    d = os.path.join(base, "nfstr_data")
    os.makedirs(d, exist_ok=True)
    return d


def icon_path() -> str:
    return bundled_resource("assets", "logo.png")


def cache_path() -> str:
    return os.path.join(writable_dir(), "build_cache.json")


def logs_dir() -> str:
    d = os.path.join(writable_dir(), "logs")
    os.makedirs(d, exist_ok=True)
    return d
