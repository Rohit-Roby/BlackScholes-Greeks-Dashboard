"""
Volatility-surface construction from a raw chain.

Per expiry:

1. Back out the implied forward and dividend yield from put-call parity.
2. Compute implied vols from out-of-the-money mids (puts below the forward,
   calls above). OTM options are the liquid side and carry no early-exercise
   premium, so they give the cleanest smile.
3. Fit raw SVI, weighted by vega so near-the-money quotes dominate.
4. Check butterfly arbitrage per expiry and calendar arbitrage across expiries.

The result also returns the chain enriched with a model IV for every option,
which the gamma-exposure engine uses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import bsm
from .forward import ForwardEstimate, estimate_forward
from .sources import ChainSnapshot
from .svi import SVIFit, calendar_arbitrage_free, fit_svi, implied_vol as svi_vol

logger = logging.getLogger(__name__)


@dataclass
class ExpirySlice:
    expiry: str
    T: float
    days: int
    forward: ForwardEstimate | None
    forward_used: float
    div_yield_used: float
    svi: SVIFit | None
    atm_vol: float
    skew_10: float  # vol(k=-0.10) - vol(k=+0.10): positive = put skew
    market_k: list[float] = field(default_factory=list)
    market_iv: list[float] = field(default_factory=list)
    market_strikes: list[float] = field(default_factory=list)

    def to_dict(self, n_curve: int = 81) -> dict:
        out = {
            "expiry": self.expiry,
            "T": round(self.T, 6),
            "days": self.days,
            "forward": self.forward.to_dict() if self.forward else None,
            "forward_used": round(self.forward_used, 4),
            "div_yield_used": round(self.div_yield_used, 6),
            "svi": self.svi.to_dict() if self.svi else None,
            "atm_vol": round(self.atm_vol, 6),
            "skew_10": round(self.skew_10, 6),
            "market": {
                "k": [round(x, 5) for x in self.market_k],
                "strike": self.market_strikes,
                "iv": [round(x, 5) for x in self.market_iv],
            },
        }
        if self.svi and self.market_k:
            lo, hi = min(self.market_k), max(self.market_k)
            ks = np.linspace(lo, hi, n_curve)
            out["curve"] = {
                "k": [round(float(x), 5) for x in ks],
                "strike": [round(float(self.forward_used * np.exp(x)), 4) for x in ks],
                "iv": [round(float(v), 5) for v in svi_vol(ks, self.T, self.svi.params)],
            }
        return out


@dataclass
class SurfaceResult:
    symbol: str
    spot: float
    rate: float
    slices: list[ExpirySlice]
    calendar_ok: bool
    calendar_violations: list[dict]
    chain: pd.DataFrame  # enriched with iv, forward, q, k

    def slice_for(self, expiry: str) -> ExpirySlice:
        for s in self.slices:
            if s.expiry == expiry:
                return s
        raise KeyError(expiry)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "spot": round(self.spot, 4),
            "rate": self.rate,
            "calendar_ok": self.calendar_ok,
            "calendar_violations": self.calendar_violations,
            "slices": [s.to_dict() for s in self.slices],
        }


def _mid(df: pd.DataFrame) -> np.ndarray:
    bid, ask, last = (df[c].to_numpy(dtype=float) for c in ("bid", "ask", "last"))
    mid = np.where((bid > 0) & (ask >= bid), (bid + ask) / 2.0, last)
    return mid


def build_surface(snap: ChainSnapshot, min_days: int = 1) -> SurfaceResult:
    spot, r = snap.spot, snap.rate
    slices: list[ExpirySlice] = []
    enriched = []

    for expiry, grp in snap.chain.groupby("expiry", sort=True):
        T = float(grp["T"].iloc[0])
        days = int(round(T * 365))
        if days < min_days:
            continue
        fwd = estimate_forward(grp, spot, r)
        if fwd is not None and 0.5 * spot < fwd.forward < 1.5 * spot:
            F, q = fwd.forward, fwd.implied_div_yield
        else:
            F, q = spot * np.exp(r * T), 0.0

        g = grp.copy()
        g["mid"] = _mid(g)
        g["k"] = np.log(g["strike"] / F)
        g["forward"] = F
        g["q"] = q
        g["iv"] = bsm.implied_vol_array(g["mid"], spot, g["strike"], T, r, q, g["is_call"])

        # OTM smile: puts with K < F, calls with K >= F; drop sub-penny and absurd quotes.
        otm = g[(g["is_call"] & (g["strike"] >= F)) | (~g["is_call"] & (g["strike"] < F))]
        otm = otm[np.isfinite(otm["iv"]) & (otm["mid"] >= 0.05) & (otm["iv"].between(0.01, 4.0))]
        otm = otm[otm["k"].abs() <= max(0.6, 4 * np.nanmedian(otm["iv"]) * np.sqrt(T))].sort_values("k")

        svi_fit = None
        if len(otm) >= 5:
            weights = bsm.vega(spot, otm["strike"], T, r, q, otm["iv"])
            try:
                svi_fit = fit_svi(otm["k"].to_numpy(), otm["iv"].to_numpy(), T, weights)
            except Exception as exc:  # pragma: no cover - logged, slice still returned
                logger.warning("SVI fit failed for %s %s: %s", snap.symbol, expiry, exc)

        if svi_fit:
            atm_vol = float(svi_vol(np.array([0.0]), T, svi_fit.params)[0])
            skew = float(svi_vol(np.array([-0.10]), T, svi_fit.params)[0]
                         - svi_vol(np.array([0.10]), T, svi_fit.params)[0])
            # Fill model IV for every listed strike (used by GEX), smoothing out bad quotes.
            g["model_iv"] = svi_vol(g["k"].to_numpy(), T, svi_fit.params)
        else:
            near = otm[otm["k"].abs() < 0.05]["iv"]
            atm_vol = float(near.mean()) if len(near) else float("nan")
            skew = float("nan")
            g["model_iv"] = g["iv"].fillna(g["vendor_iv"])

        enriched.append(g)
        slices.append(ExpirySlice(
            expiry=str(expiry), T=T, days=days, forward=fwd, forward_used=float(F),
            div_yield_used=float(q), svi=svi_fit, atm_vol=atm_vol, skew_10=skew,
            market_k=otm["k"].tolist(), market_iv=otm["iv"].tolist(),
            market_strikes=otm["strike"].tolist(),
        ))

    fits = [(s.T, s.svi.params) for s in slices if s.svi]
    cal_ok, cal_viol = calendar_arbitrage_free(fits) if len(fits) > 1 else (True, [])
    chain = pd.concat(enriched, ignore_index=True) if enriched else snap.chain.iloc[0:0]
    return SurfaceResult(symbol=snap.symbol, spot=spot, rate=r, slices=slices,
                         calendar_ok=cal_ok, calendar_violations=cal_viol, chain=chain)
