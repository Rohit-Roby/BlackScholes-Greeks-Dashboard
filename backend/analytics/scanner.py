"""
Daily volatility scanner: rank a universe of optionable names and return the
top N "most volatile option markets" with the context needed to dig in.

For each symbol the scanner records:

* ATM implied vol of the nearest expiry at least ``min_days`` out (from SVI)
* 20-day realised vol and the IV / RV ratio (is volatility rich or cheap?)
* 1σ expected move to that expiry, in % of spot
* total option volume, open interest and the put/call volume ratio
* dealer gamma regime and the distance to the call and put walls

Symbols are fetched concurrently because live sources are I/O bound. A symbol
that fails (no options, bad data) is reported in ``errors`` instead of
breaking the whole scan.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from .gex import compute_gex
from .sources import ChainSource, realised_vol
from .surface import build_surface

logger = logging.getLogger(__name__)

DEFAULT_UNIVERSE = [
    "SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META", "AMZN",
    "GOOGL", "NFLX", "AVGO", "COIN", "PLTR", "MSTR", "SMCI", "UBER", "BA", "JPM",
]

SORT_KEYS = {
    "atm_iv": "ATM implied volatility",
    "iv_rv": "Implied / realised volatility ratio",
    "expected_move": "1σ expected move (% of spot)",
    "volume": "Total option volume",
}


def scan_symbol(source: ChainSource, symbol: str, min_days: int = 5) -> dict:
    snap = source.snapshot(symbol, max_expiries=3, max_days=60)
    surface = build_surface(snap)
    if not surface.slices:
        raise ValueError("no usable expiries")
    sl = next((s for s in surface.slices if s.days >= min_days), surface.slices[0])
    rv = realised_vol(snap.closes, 20)
    gex = compute_gex(surface.chain, snap.spot, snap.rate)
    front = snap.chain[snap.chain["expiry"] == sl.expiry]
    call_vol = float(front.loc[front["is_call"], "volume"].sum())
    put_vol = float(front.loc[~front["is_call"], "volume"].sum())
    em_pct = sl.atm_vol * np.sqrt(sl.T) * 100

    def dist(level):
        return None if level is None else round((level / snap.spot - 1) * 100, 2)

    return {
        "symbol": snap.symbol,
        "spot": round(snap.spot, 2),
        "expiry": sl.expiry,
        "days": sl.days,
        "atm_iv": round(sl.atm_vol, 4),
        "rv20": round(rv, 4) if np.isfinite(rv) else None,
        "iv_rv": round(sl.atm_vol / rv, 3) if np.isfinite(rv) and rv > 0 else None,
        "skew_10": round(sl.skew_10, 4) if np.isfinite(sl.skew_10) else None,
        "expected_move": round(em_pct, 2),
        "volume": int(call_vol + put_vol),
        "open_interest": int(front["open_interest"].sum()),
        "put_call_ratio": round(put_vol / call_vol, 3) if call_vol > 0 else None,
        "gamma_regime": gex.regime,
        "call_wall": gex.call_wall,
        "put_wall": gex.put_wall,
        "gamma_flip": None if gex.gamma_flip is None else round(gex.gamma_flip, 2),
        "call_wall_dist_pct": dist(gex.call_wall),
        "put_wall_dist_pct": dist(gex.put_wall),
        "source": snap.source,
        "asof": snap.asof,
    }


def scan(source: ChainSource, universe: list[str] | None = None, top: int = 10,
         sort_by: str = "atm_iv", max_workers: int = 8) -> dict:
    if sort_by not in SORT_KEYS:
        raise ValueError(f"sort_by must be one of {list(SORT_KEYS)}")
    universe = [s.strip().upper() for s in (universe or DEFAULT_UNIVERSE) if s.strip()]
    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(scan_symbol, source, s): s for s in universe}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                rows.append(fut.result())
            except Exception as exc:
                logger.warning("scan failed for %s: %s", sym, exc)
                errors.append({"symbol": sym, "error": str(exc)})

    rows.sort(key=lambda r: (r.get(sort_by) is None, -(r.get(sort_by) or 0)))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {"sort_by": sort_by, "sort_label": SORT_KEYS[sort_by], "scanned": len(universe),
            "results": rows[:top], "errors": sorted(errors, key=lambda e: e["symbol"])}
