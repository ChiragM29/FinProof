"""Hybrid mode: online first, the local cache whenever the network is not there.

FINPROOF_OFFLINE=1 forces cache-only (rehearsed demos). Otherwise FinProof tries the network and
falls back to the cache on any failure; `online()` tells the header whether it is LIVE or on CACHE.
"""

from __future__ import annotations

import socket
import threading
import time

from . import config

PROBE_HOSTS = (("www.youtube.com", 443), ("query1.finance.yahoo.com", 443))
PROBE_TIMEOUT = 1.5
PROBE_TTL = 30.0  # seconds a probe result is reused

_lock = threading.Lock()
_last = {"at": 0.0, "ok": False}


def _probe() -> bool:
    for host, port in PROBE_HOSTS:
        try:
            with socket.create_connection((host, port), timeout=PROBE_TIMEOUT):
                return True
        except OSError:
            continue
    return False


def online(force_check: bool = False) -> bool:
    """True when the network answers (cached for PROBE_TTL seconds). Always False when offline is forced."""
    if config.OFFLINE:
        return False
    with _lock:
        if force_check or time.monotonic() - _last["at"] > PROBE_TTL:
            _last["ok"], _last["at"] = _probe(), time.monotonic()
        return _last["ok"]


def mark_offline() -> None:
    """A fetch just failed for network reasons: show CACHE until the next probe."""
    with _lock:
        _last["ok"], _last["at"] = False, time.monotonic()


def status() -> dict:
    live = online()
    return {"mode": "hybrid", "live": live, "label": "HYBRID · LIVE" if live else "HYBRID · CACHE",
            "offline_forced": config.OFFLINE}
