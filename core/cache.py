"""
core/cache.py
Tiny disk cache: { sha256_of_exe: { signature_id: rva } }.

Once a build has been calibrated (every signature resolved + verified),
future launches against that exact same exe skip AOB scanning entirely
and go straight to the known-good RVA. Delete the cache file, or a
single build's entry, to force a fresh scan (e.g. after a game update).
"""

from __future__ import annotations

import json
import os
from typing import Optional


class BuildCache:
    def __init__(self, path: str):
        self.path = path
        self._data: dict[str, dict[str, int]] = {}
        self.load()

    def load(self):
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=1)
        os.replace(tmp, self.path)

    def get(self, sha256: Optional[str], sig_id: str) -> Optional[int]:
        if not sha256:
            return None
        return self._data.get(sha256, {}).get(sig_id)

    def set(self, sha256: Optional[str], sig_id: str, rva: int):
        if not sha256:
            return
        self._data.setdefault(sha256, {})[sig_id] = rva

    def known_builds(self) -> list[str]:
        return list(self._data.keys())

    def forget_build(self, sha256: str):
        self._data.pop(sha256, None)
