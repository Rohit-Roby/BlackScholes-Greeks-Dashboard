"""
Walk-forward check of the market outlook against what happened next.

For every (symbol, day) the outlook is rebuilt from that day's closing option
chain only (open interest published that morning, quotes in the last ten
minutes before the close), then compared with the next session's close.

Reported:

* **Direction hit rate** on the days the model leaned (|score| >= threshold).
* **Brier score** of P(up) against a coin flip (0.25). Lower is better.
* **Range coverage**: how often the next close landed inside the next-session
  range, against the probability the model gave it.
* **Realised / implied move** by gamma regime: whether long gamma really did
  shrink moves and short gamma enlarge them. This is the evidence for
  ``RANGE_MULT``.

With a short history these numbers are noisy; the summary says so.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from .gex import compute_gex
from .outlook import build_outlook
from .sources import ChainSnapshot, realised_vol
from .surface import build_surface

logger = logging.getLogger(__name__)


def observe(snap: ChainSnapshot, next_close: float) -> dict:
    surface = build_surface(snap)
    gex = compute_gex(surface.chain, snap.spot, snap.rate)
    out = build_outlook(snap, surface, gex, realised_vol(snap.closes, 20))
    h = out["horizons"][0]
    ret = next_close / snap.spot - 1
    return {
        "date": snap.asof[:10], "symbol": snap.symbol, "spot": snap.spot, "next_close": next_close,
        "ret": ret, "up": bool(ret > 0), "p_up": out["direction"]["p_up"],
        "score": out["direction"]["score"], "lean": out["direction"]["label"],
        "regime": out["regime"]["gamma"], "low": h["low"], "high": h["high"],
        "p_inside": h["p_inside"], "inside": bool(h["low"] <= next_close <= h["high"]),
        "implied_move": h["implied_move"],
        "move_ratio": abs(next_close - snap.spot) / h["implied_move"] if h["implied_move"] else None,
    }


def summarise(records: list[dict]) -> dict:
    if not records:
        return {"n": 0}
    df = pd.DataFrame(records)
    leaned = df[df["lean"] != "Neutral"]
    hits = ((leaned["lean"] == "Lean up") == leaned["up"]) if len(leaned) else pd.Series(dtype=bool)
    brier = float(((df["p_up"] - df["up"].astype(float)) ** 2).mean())
    by_regime = {}
    for regime, g in df.groupby("regime"):
        by_regime[regime] = {"n": int(len(g)),
                             "median_move_ratio": round(float(g["move_ratio"].median()), 3),
                             "range_coverage": round(float(g["inside"].mean()), 3)}
    n = len(df)
    return {
        "n": n,
        "symbols": sorted(df["symbol"].unique().tolist()),
        "start": str(df["date"].min()), "end": str(df["date"].max()),
        "leaned": int(len(leaned)),
        "direction_hit_rate": round(float(hits.mean()), 3) if len(leaned) else None,
        "up_day_rate": round(float(df["up"].mean()), 3),
        "brier": round(brier, 4), "brier_coin_flip": 0.25,
        "range_coverage": round(float(df["inside"].mean()), 3),
        "range_nominal": round(float(df["p_inside"].mean()), 3),
        "by_regime": by_regime,
        "reliability": ("too few observations to trust: treat as a smoke test" if n < 60 else
                        "small sample: indicative only" if n < 250 else "reasonable sample"),
    }


def run(symbols: Iterable[str], days: Iterable[date],
        snapshot_for: Callable[[str, date], ChainSnapshot],
        next_close_for: Callable[[str, date], float | None]) -> dict:
    records, errors = [], []
    for day in days:
        for sym in symbols:
            try:
                nxt = next_close_for(sym, day)
                if nxt is None:
                    continue
                records.append(observe(snapshot_for(sym, day), nxt))
                logger.info("backtest %s %s ok", sym, day)
            except Exception as exc:  # keep going; report what failed
                logger.warning("backtest %s %s failed: %s", sym, day, exc)
                errors.append({"symbol": sym, "date": day.isoformat(), "error": str(exc)[:200]})
    return {"summary": summarise(records), "records": records, "errors": errors}


def _clean(x):
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else round(float(x), 6)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


def to_json_ready(result: dict) -> dict:
    return _clean(result)
