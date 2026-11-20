"""
Thin service layer between the API routes and the analytics package.

* Picks the chain source (``CHAIN_SOURCE`` env var, default ``yahoo``) and the
  risk-free rate (``RISK_FREE_RATE``, default 0.04).
* Caches snapshots and analyses for ``ANALYTICS_CACHE_TTL`` seconds (default
  300) so the dashboard does not hammer the data vendor on every click.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

from .gex import compute_gex
from .scanner import DEFAULT_UNIVERSE, SORT_KEYS, scan
from .scenarios import STRATEGIES, run_scenarios
from .sources import ChainSnapshot, get_source, realised_vol
from .surface import build_surface

DEFAULT_SOURCE = os.getenv("CHAIN_SOURCE", "yahoo").lower()
RISK_FREE_RATE = float(os.getenv("RISK_FREE_RATE", "0.04"))
CACHE_TTL = int(os.getenv("ANALYTICS_CACHE_TTL", "300"))


class TTLCache:
    def __init__(self, ttl: int):
        self.ttl = ttl
        self._data: dict[tuple, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_set(self, key: tuple, fn: Callable[[], Any]) -> Any:
        now = time.time()
        with self._lock:
            hit = self._data.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        value = fn()
        with self._lock:
            self._data[key] = (time.time(), value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


cache = TTLCache(CACHE_TTL)


def _source_name(source: str | None) -> str:
    return (source or DEFAULT_SOURCE).lower()


def snapshot(symbol: str, source: str | None = None) -> ChainSnapshot:
    src = _source_name(source)
    return cache.get_or_set(("snap", src, symbol.upper()),
                            lambda: get_source(src, RISK_FREE_RATE).snapshot(symbol.upper()))


def _analysis(symbol: str, source: str | None):
    src = _source_name(source)

    def compute():
        snap = snapshot(symbol, src)
        surface = build_surface(snap)
        if not surface.slices:
            raise ValueError(f"No usable option expiries for {symbol}")
        gex = compute_gex(surface.chain, snap.spot, snap.rate)
        return snap, surface, gex, realised_vol(snap.closes, 20)

    return cache.get_or_set(("analysis", src, symbol.upper()), compute)


def analyze(symbol: str, source: str | None = None) -> dict:
    snap, surface, gex, rv20 = _analysis(symbol, source)
    front = next((s for s in surface.slices if s.days >= 5), surface.slices[0])
    return {
        "symbol": snap.symbol,
        "source": snap.source,
        "asof": snap.asof,
        "spot": round(snap.spot, 4),
        "rate": snap.rate,
        "rv20": round(rv20, 4) if rv20 == rv20 else None,
        "front_expiry": front.expiry,
        "front_atm_iv": round(front.atm_vol, 4),
        "surface": surface.to_dict(),
        "gex": gex.to_dict(),
        "expiries": [s.expiry for s in surface.slices],
        "strikes": {s.expiry: sorted(surface.chain.loc[surface.chain["expiry"] == s.expiry, "strike"]
                                     .unique().tolist()) for s in surface.slices},
    }


def scenarios(symbol: str, strategy: str, expiry: str | None = None, strike: float | None = None,
              iv_shift: float = 0.0, source: str | None = None) -> dict:
    _, surface, gex, rv20 = _analysis(symbol, source)
    return run_scenarios(surface, gex, rv20, strategy, expiry, strike, iv_shift)


def scanner(symbols: list[str] | None = None, top: int = 10, sort_by: str = "atm_iv",
            source: str | None = None) -> dict:
    src = _source_name(source)
    key = ("scan", src, tuple(symbols or DEFAULT_UNIVERSE), top, sort_by)
    result = cache.get_or_set(key, lambda: scan(get_source(src, RISK_FREE_RATE), symbols, top, sort_by))
    return {"source": src, **result}


def meta() -> dict:
    return {
        "default_source": DEFAULT_SOURCE,
        "sources": ["yahoo", "synthetic"],
        "risk_free_rate": RISK_FREE_RATE,
        "default_universe": DEFAULT_UNIVERSE,
        "sort_keys": SORT_KEYS,
        "strategies": list(STRATEGIES),
        "cache_ttl_seconds": CACHE_TTL,
    }
