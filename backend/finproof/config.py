"""Paths and settings shared by every module."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Read KEY=VALUE lines from finproof/.env (never committed) without overriding real env vars."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")
DATA = ROOT / "data"
REAL = DATA / "real"
SYNTHETIC = DATA / "synthetic"
CACHE = DATA / "cache"
DASHBOARD = ROOT / "dashboard"

# A source needs at least this many scored tips before we show a percentage.
MIN_TIPS_FOR_RECORD = 10

# Days after a tip at which we compare the stock with the Nifty 50.
HORIZONS = (7, 30, 90)
MAIN_HORIZON = 30

BENCHMARK = "^NSEI"  # Nifty 50 on Yahoo Finance

# Set FINPROOF_OFFLINE=1 to use only cached prices and transcripts (demo safety).
OFFLINE = os.environ.get("FINPROOF_OFFLINE", "") == "1"

REAL_LABEL = "REAL"
SYNTHETIC_LABEL = "SYNTHETIC"
