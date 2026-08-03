from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict, fields
from typing import Any

from core import paths

log = logging.getLogger("nfstr.settings")

SETTINGS_FILENAME = "settings.json"


@dataclass
class Settings:
    theme: str = "dark"
    start_minimized: bool = False
    auto_attach: bool = True
    remember_window_size: bool = True
    remember_selected_category: bool = True
    enable_notifications: bool = True
    reduced_motion: bool = False


    window_width: int = 1180
    window_height: int = 760
    last_category: str = ""
    favorite_vehicle_entries: list | None = None


    feature_values: dict | None = None

    def __post_init__(self):
        if self.favorite_vehicle_entries is None:
            self.favorite_vehicle_entries = []
        if self.feature_values is None:
            self.feature_values = {}


def _settings_path() -> str:
    return os.path.join(paths.writable_dir(), SETTINGS_FILENAME)


def load() -> Settings:
    path = _settings_path()
    if not os.path.isfile(path):
        return Settings()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw: dict[str, Any] = json.load(f)
        known = {f.name for f in fields(Settings)}
        filtered = {k: v for k, v in raw.items() if k in known}
        return Settings(**filtered)
    except Exception:
        log.exception("Failed to load settings.json, using defaults")
        return Settings()


def save(settings: Settings) -> None:
    path = _settings_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, indent=2)
    except Exception:
        log.exception("Failed to save settings.json")
