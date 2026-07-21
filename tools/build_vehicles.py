#!/usr/bin/env python3
"""
tools/build_vehicles.py

Regenerates data/vehicles.json from data/vehicles_raw.csv (a straight
copy of resources/Vehicle Library/vehicle customization library.csv --
credited to _mRally2, see README.md Credits).

Each row's "HASH ID" column is 4 space-separated hex bytes as Cheat
Engine displays a little-endian dword, e.g. "27 55 4E A2" -> the u32
value used by the Car Object pointer chain (see
tools/build_signatures.py's vehicle_swap_car_object entry).
"""

from __future__ import annotations

import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_PATH = os.path.join(HERE, "..", "data", "vehicles_raw.csv")
OUT_PATH = os.path.join(HERE, "..", "data", "vehicles.json")


def main():
    rows = []
    section = "Base Game"
    with open(RAW_PATH, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # header
        for row in reader:
            if not row or all(not c.strip() for c in row):
                continue
            name, dbentry, hashid = (row + ["", ""])[:3]
            name, dbentry, hashid = name.strip(), dbentry.strip(), hashid.strip()
            if not dbentry and not hashid:
                section = name  # a section header row, e.g. "Unreleased"
                continue
            if not hashid:
                continue
            parts = hashid.split()
            if len(parts) != 4:
                continue
            try:
                b = bytes(int(h, 16) for h in parts)
            except ValueError:
                continue
            rows.append(dict(
                vehicle=name, entry=dbentry, hash_hex=hashid,
                hash_u32=int.from_bytes(b, "little"), section=section,
            ))

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    print(f"Wrote {len(rows)} vehicles -> {OUT_PATH}")


if __name__ == "__main__":
    main()
