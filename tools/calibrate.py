#!/usr/bin/env python3
"""
tools/calibrate.py

Run this first, before the GUI, whenever you're on a game build that
hasn't been seen before (or after a game update). It attaches, resolves
every signature (AOB scan first, RVA fallback, byte-verified), prints a
full report, and saves everything that verified to the on-disk cache
(data/build_cache.json) so the GUI's next launch is instant.

Usage:
    python tools/calibrate.py
    python tools/calibrate.py --wait          # poll until the game is running
    python tools/calibrate.py --forget-cache  # ignore/overwrite any existing cache entry for this build
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import process
from core import paths
from core.cache import BuildCache
from core.resolver import SignatureResolver

SIGNATURES_PATH = paths.bundled_resource("data", "signatures.json")
CACHE_PATH = paths.cache_path()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wait", action="store_true", help="poll until the game process appears")
    ap.add_argument("--forget-cache", action="store_true",
                      help="ignore this build's existing cache entry and re-scan everything")
    ap.add_argument("--verbose", action="store_true", help="enable debug-level logging")
    args = ap.parse_args()

    from core import logging_setup
    log_path = logging_setup.setup_logging(verbose=args.verbose)
    print(f"(full log also being written to {log_path})\n")

    print("Looking for the game process...")
    try:
        target = process.attach(timeout=(3600 if args.wait else 0))
    except ProcessLookupError as e:
        print(f"ERROR: {e}")
        print("Start the game first, or run with --wait to poll until it appears.")
        sys.exit(1)

    print(f"Attached to PID {target.pid} ({target.process_name})")
    print(f"Module base: {hex(target.base)}  size: {hex(target.size)}")
    print(f"Exe path:    {target.exe_path}")
    print(f"SHA256:      {target.sha256}")
    if target.delta:
        print(f"Note: module is loaded {hex(abs(target.delta))} "
              f"{'above' if target.delta > 0 else 'below'} the historical reference base -- "
              f"this is normal and handled automatically.")

    with open(SIGNATURES_PATH, "r", encoding="utf-8") as f:
        signatures = json.load(f)

    cache = BuildCache(CACHE_PATH)
    if args.forget_cache and target.sha256:
        cache.forget_build(target.sha256)

    resolver = SignatureResolver(target, signatures, cache)

    def progress(i, total, sid, result):
        flag = "OK" if result.verified else ("--" if result.method != "missing" else "??")
        print(f"  [{i:3}/{total}] [{flag}] {sid:<32} via {result.method:<6} "
              f"{hex(result.address) if result.address else '':<12} {result.detail}")

    print("\nResolving signatures (AOB scan first, RVA fallback)...\n")
    resolver.resolve_all(progress_cb=progress)

    print()
    print(resolver.summary())
    print(f"\nCache saved to {CACHE_PATH}")
    print("You can now launch the GUI (python main.py) -- it will reuse this "
          "cache and skip straight to these addresses.")


if __name__ == "__main__":
    main()
