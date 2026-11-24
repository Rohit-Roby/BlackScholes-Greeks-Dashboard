"""
Option-chain data sources.

Every source returns a :class:`ChainSnapshot`: spot, a history of closes for
realised volatility, and one tidy DataFrame of quotes with a fixed schema:

    symbol, expiry, T, strike, is_call, bid, ask, last, volume, open_interest, vendor_iv

Two sources ship with the project:

* :class:`YahooChainSource` pulls live chains through ``yfinance``.
* :class:`SyntheticChainSource` builds a realistic, deterministic chain from a
  known SVI smile, dividend yield and planted open-interest walls. It lets the
  dashboard run offline (demos, CI) and gives the tests a ground truth.

New vendors plug in by subclassing :class:`ChainSource`.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import bsm
from .svi import SVIParams, implied_vol as svi_vol

logger = logging.getLogger(__name__)

CHAIN_COLUMNS = ["symbol", "expiry", "T", "strike", "is_call", "bid", "ask", "last",
                 "volume", "open_interest", "vendor_iv"]


@dataclass
class ChainSnapshot:
    symbol: str
    spot: float
    rate: float
    asof: str
    chain: pd.DataFrame
    closes: pd.Series
    source: str
    truth: dict = field(default_factory=dict)  # only set by the synthetic source

    @property
    def expiries(self) -> list[str]:
        return sorted(self.chain["expiry"].unique().tolist())


def realised_vol(closes: pd.Series, window: int = 20) -> float:
    """Annualised close-to-close realised volatility over the last ``window`` days."""
    rets = np.diff(np.log(closes.to_numpy(dtype=float)))[-window:]
    if len(rets) < 5:
        return float("nan")
    return float(np.std(rets, ddof=1) * np.sqrt(252))


class ChainSource(ABC):
    name: str = "base"

    @abstractmethod
    def snapshot(self, symbol: str, max_expiries: int = 6, max_days: int = 120) -> ChainSnapshot:
        """Return a chain snapshot for ``symbol``."""


# --------------------------------------------------------------------------- Yahoo


class YahooChainSource(ChainSource):
    """Live option chains from Yahoo Finance (delayed, best-effort quality)."""

    name = "yahoo"

    def __init__(self, rate: float = 0.04):
        self.rate = rate

    def snapshot(self, symbol: str, max_expiries: int = 6, max_days: int = 120) -> ChainSnapshot:
        import yfinance as yf  # imported lazily so the package works without it

        tkr = yf.Ticker(symbol)
        hist = tkr.history(period="6mo")
        if hist.empty:
            raise ValueError(f"No price history for {symbol}")
        closes = hist["Close"].dropna()
        spot = float(closes.iloc[-1])

        today = date.today()
        expiries = []
        for exp in tkr.options:
            days = (date.fromisoformat(exp) - today).days
            if 0 <= days <= max_days:
                expiries.append(exp)
        if not expiries:
            raise ValueError(f"No listed options for {symbol} within {max_days} days")

        frames = []
        for exp in expiries[:max_expiries]:
            oc = tkr.option_chain(exp)
            days = (date.fromisoformat(exp) - today).days
            T = max(days + 0.5, 0.5) / 365.0  # half a day for same-day expiries
            for df, is_call in ((oc.calls, True), (oc.puts, False)):
                if df is None or df.empty:
                    continue
                frames.append(pd.DataFrame({
                    "symbol": symbol,
                    "expiry": exp,
                    "T": T,
                    "strike": df["strike"].astype(float),
                    "is_call": is_call,
                    "bid": df["bid"].fillna(0.0).astype(float),
                    "ask": df["ask"].fillna(0.0).astype(float),
                    "last": df["lastPrice"].fillna(0.0).astype(float),
                    "volume": df["volume"].fillna(0).astype(float),
                    "open_interest": df["openInterest"].fillna(0).astype(float),
                    "vendor_iv": df["impliedVolatility"].astype(float),
                }))
        chain = pd.concat(frames, ignore_index=True)[CHAIN_COLUMNS]
        return ChainSnapshot(symbol=symbol, spot=spot, rate=self.rate,
                             asof=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             chain=chain, closes=closes, source=self.name)


# --------------------------------------------------------------------------- Synthetic


def _seed(symbol: str, day: date) -> int:
    return int(hashlib.sha256(f"{symbol}|{day.isoformat()}".encode()).hexdigest()[:8], 16)


def _strike_step(spot: float) -> float:
    for limit, step in ((25, 0.5), (100, 1.0), (250, 2.5), (1000, 5.0)):
        if spot < limit:
            return step
    return 10.0


class SyntheticChainSource(ChainSource):
    """
    Deterministic synthetic chains with known ground truth.

    Each symbol gets its own volatility level, skew, dividend yield and two
    open-interest "walls" (a call-heavy strike above spot and a put-heavy strike
    below). The same symbol and day always produce the same chain.
    """

    name = "synthetic"
    EXPIRY_DAYS = (7, 14, 30, 60, 90)

    def __init__(self, rate: float = 0.04, asof: date | None = None):
        self.rate = rate
        self.asof = asof or date(2026, 11, 20)

    def snapshot(self, symbol: str, max_expiries: int = 6, max_days: int = 120) -> ChainSnapshot:
        rng = np.random.default_rng(_seed(symbol.upper(), self.asof))
        spot = float(np.round(rng.uniform(20, 600), 2))
        index_like = symbol.upper() in {"SPY", "QQQ", "IWM", "DIA", "XSP", "SPX", "NDX"}
        base_vol = float(rng.uniform(0.11, 0.24) if index_like else rng.uniform(0.18, 0.70))
        rho = float(rng.uniform(-0.75, -0.15))
        q = float(rng.choice([0.0, 0.0, rng.uniform(0.005, 0.035)]))
        step = _strike_step(spot)
        atm = round(spot / step) * step
        call_wall = atm + step * int(rng.integers(2, 6))
        put_wall = atm - step * int(rng.integers(2, 6))

        rows = []
        truth = {"q": q, "base_vol": base_vol, "rho": rho,
                 "call_wall": call_wall, "put_wall": put_wall, "svi": {}}
        for days in [d for d in self.EXPIRY_DAYS if d <= max_days][:max_expiries]:
            T = days / 365.0
            expiry = (self.asof + timedelta(days=days)).isoformat()
            F = spot * np.exp((self.rate - q) * T)
            # Term structure: short end slightly richer for high-vol names.
            atm_var = (base_vol * (1 + 0.15 * np.exp(-days / 20))) ** 2 * T
            s = 0.08 + 0.15 * np.sqrt(T)
            b = 0.6 * base_vol * np.sqrt(T) / (1 + abs(rho))
            a = atm_var - b * s  # so that w(0) = a + b*s = atm_var
            p = SVIParams(a=float(a), b=float(b), rho=rho, m=0.0, s=float(s))
            truth["svi"][expiry] = p.to_dict()

            width = max(0.25, 3.0 * base_vol * np.sqrt(T))
            ks = np.arange(atm * np.exp(-width), atm * np.exp(width) + step, step)
            ks = np.round(ks / step) * step
            ks = np.unique(ks[ks > 0])
            k_log = np.log(ks / F)
            vols = svi_vol(k_log, T, p)
            for is_call in (True, False):
                fair = bsm.price(spot, ks, T, self.rate, q, vols, is_call)
                spread = np.maximum(0.01, 0.03 * fair + 0.005 * spot * base_vol * 0.1)
                noise = rng.normal(0, 0.1, len(ks)) * spread
                mid = np.maximum(fair + noise, 0.01)
                bid = np.maximum(np.round(mid - spread / 2, 2), 0.0)
                ask = np.round(mid + spread / 2, 2)
                dist = (ks - spot) / (spot * base_vol * np.sqrt(T) + 1e-9)
                oi = 4000 * np.exp(-0.5 * dist**2) * (1.4 if not is_call else 1.0)
                wall = call_wall if is_call else put_wall
                oi += 60000 * np.exp(-0.5 * ((ks - wall) / step) ** 2) * np.exp(-days / 45)
                oi = np.round(oi * rng.uniform(0.7, 1.3, len(ks)))
                vol = np.round(oi * rng.uniform(0.05, 0.6, len(ks)))
                rows.append(pd.DataFrame({
                    "symbol": symbol.upper(), "expiry": expiry, "T": T, "strike": ks,
                    "is_call": is_call, "bid": bid, "ask": ask, "last": np.round(mid, 2),
                    "volume": vol, "open_interest": oi, "vendor_iv": vols,
                }))

        chain = pd.concat(rows, ignore_index=True)[CHAIN_COLUMNS]
        n = 130
        rv = base_vol * rng.uniform(0.7, 1.2)
        rets = rng.normal(0, rv / np.sqrt(252), n)
        log_path = np.cumsum(rets)
        path = spot * np.exp(log_path - log_path[-1])  # random walk that ends at spot
        idx = pd.bdate_range(end=pd.Timestamp(self.asof), periods=n)
        closes = pd.Series(path, index=idx, name="Close")
        return ChainSnapshot(symbol=symbol.upper(), spot=spot, rate=self.rate,
                             asof=f"{self.asof.isoformat()}T16:00:00+00:00",
                             chain=chain, closes=closes, source=self.name, truth=truth)


def get_source(name: str, rate: float = 0.04) -> ChainSource:
    name = (name or "synthetic").lower()
    if name == "yahoo":
        return YahooChainSource(rate=rate)
    if name == "synthetic":
        return SyntheticChainSource(rate=rate)
    if name == "databento":
        from .databento_source import DatabentoChainSource  # optional dependency
        return DatabentoChainSource(rate=rate)
    raise ValueError(f"Unknown chain source '{name}'. Use 'yahoo', 'databento' or 'synthetic'.")
