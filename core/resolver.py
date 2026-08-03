from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from .process import TargetProcess
from .scanner import AOBScanner
from .cache import BuildCache

log = logging.getLogger("nfstr.resolver")


@dataclass
class Resolved:
    entry_id: str
    address: Optional[int]
    method: str
    verified: bool
    detail: str = ""


class SignatureResolver:
    def __init__(self, target: TargetProcess, signatures: list[dict], cache: BuildCache):
        self.target = target
        self.sigs = {s["id"]: s for s in signatures}
        self.cache = cache
        self.scanner = AOBScanner(target.pm.process_handle)
        self.resolved: dict[str, Resolved] = {}

    def resolve_all(self, progress_cb=None) -> dict[str, Resolved]:
        total = len(self.sigs)
        log.info("Resolving %d signatures for module base=%s size=%s sha256=%s",
                  total, hex(self.target.base), hex(self.target.size), self.target.sha256)
        for i, (sid, sig) in enumerate(self.sigs.items()):
            try:
                r = self.resolve_one(sig)
            except Exception:
                log.exception("Unexpected error resolving %s -- treating as unresolved", sid)
                r = Resolved(sid, None, "missing", False, "unexpected error during resolution")
            self.resolved[sid] = r
            level = logging.DEBUG if r.verified else logging.WARNING
            log.log(level, "[%d/%d] %-32s method=%-6s addr=%s verified=%s %s",
                      i + 1, total, sid, r.method,
                      hex(r.address) if r.address is not None else "n/a",
                      r.verified, r.detail)
            if progress_cb:
                progress_cb(i + 1, total, sid, r)
        self.cache.save()
        ok = sum(1 for r in self.resolved.values() if r.verified)
        log.info("Resolution complete: %d/%d verified", ok, total)
        return self.resolved

    def resolve_one(self, sig: dict) -> Resolved:
        sid = sig["id"]

        if sig.get("patch_type") == "cave_field_freeze":


            return Resolved(sid, None, "n/a", True,
                             f"address-less: rides on cave_ref={sig.get('cave_ref')!r} at enable time")

        cached_rva = self.cache.get(self.target.sha256, sid)
        if cached_rva is not None:
            addr = self.target.addr(cached_rva)
            ok = self._verify(sig, addr)
            if ok:
                return Resolved(sid, addr, "cache", True)
            log.warning("cache hit for %s failed verification, re-resolving", sid)

        addr = None
        method = "missing"

        aob = sig.get("aob")
        if aob:
            hit = self.scanner.scan_unique(self.target.base, self.target.size, aob)
            if hit is not None:
                addr = hit + sig.get("aob_result_offset", 0)
                method = "scan"

        if addr is None and sig.get("historical_rva") is not None:
            addr = self.target.addr(sig["historical_rva"])
            method = "rva"

        if addr is None:
            return Resolved(sid, None, "missing", False, "no scan hit and no RVA fallback")

        ok = self._verify(sig, addr)
        if ok and self.target.sha256:
            self.cache.set(self.target.sha256, sid, self.target.rva(addr))

        detail = "" if ok else "byte verification mismatch"
        return Resolved(sid, addr, method, ok, detail)

    def _verify(self, sig: dict, addr: int) -> bool:
        expected_hex = sig.get("verify_bytes")
        if not expected_hex:
            return True
        expected = bytes.fromhex(expected_hex)
        if not addr:
            return False
        try:
            actual = self.target.pm.read_bytes(addr, len(expected))
        except Exception as e:
            log.debug("verify read failed at %s: %r", hex(addr), e)
            return False
        return actual == expected

    def get(self, sid: str) -> Optional[int]:
        r = self.resolved.get(sid)
        return r.address if r and r.verified else None

    def summary(self) -> str:
        lines = []
        ok = sum(1 for r in self.resolved.values() if r.verified)
        lines.append(f"{ok}/{len(self.resolved)} signatures verified")
        for sid, r in self.resolved.items():
            flag = "OK" if r.verified else "--"
            addr_s = hex(r.address) if r.address is not None else "n/a"
            lines.append(f"  [{flag}] {sid:<28} {r.method:<6} {addr_s:<12} {r.detail}")
        return "\n".join(lines)
