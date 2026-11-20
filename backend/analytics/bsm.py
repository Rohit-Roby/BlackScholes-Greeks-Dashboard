"""
Vectorised Black-Scholes-Merton with a continuous dividend yield, plus a robust
implied-volatility solver.

The original calculator in ``backend/models/greeks_calculator.py`` prices one
option at a time with no dividends. Real equity chains need a dividend yield
(or an implied forward) and need thousands of options priced at once, so this
module works on NumPy arrays and takes ``q`` explicitly.

Conventions
-----------
* ``T`` in years, ``r`` and ``q`` continuously compounded annual rates.
* ``is_call`` is a boolean array (True = call, False = put).
* Vega is returned per 1.00 change in volatility (not per 1%).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike
from scipy.optimize import brentq
from scipy.stats import norm

_MIN_T = 1e-6
_MIN_VOL = 1e-4
_MAX_VOL = 5.0


def _d1_d2(S, K, T, r, q, sigma):
    S, K, T, r, q, sigma = np.broadcast_arrays(
        *(np.asarray(x, dtype=float) for x in (S, K, T, r, q, sigma))
    )
    T = np.maximum(T, _MIN_T)
    sigma = np.maximum(sigma, _MIN_VOL)
    vol_sqrt_t = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / vol_sqrt_t
    return d1, d1 - vol_sqrt_t, S, K, T, r, q, sigma


def price(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, q: ArrayLike,
          sigma: ArrayLike, is_call: ArrayLike) -> np.ndarray:
    """European option price under BSM with continuous dividend yield."""
    d1, d2, S, K, T, r, q, _ = _d1_d2(S, K, T, r, q, sigma)
    call = np.asarray(is_call, dtype=bool)
    df_q = np.exp(-q * T)
    df_r = np.exp(-r * T)
    call_px = S * df_q * norm.cdf(d1) - K * df_r * norm.cdf(d2)
    put_px = K * df_r * norm.cdf(-d2) - S * df_q * norm.cdf(-d1)
    return np.where(call, call_px, put_px)


def delta(S, K, T, r, q, sigma, is_call) -> np.ndarray:
    d1, _, _, _, T, _, q, _ = _d1_d2(S, K, T, r, q, sigma)
    df_q = np.exp(-q * T)
    return np.where(np.asarray(is_call, dtype=bool), df_q * norm.cdf(d1), df_q * (norm.cdf(d1) - 1.0))


def gamma(S, K, T, r, q, sigma) -> np.ndarray:
    """Gamma (identical for calls and puts)."""
    d1, _, S, _, T, _, q, sigma = _d1_d2(S, K, T, r, q, sigma)
    return np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))


def vega(S, K, T, r, q, sigma) -> np.ndarray:
    """Vega per 1.00 change in volatility (identical for calls and puts)."""
    d1, _, S, _, T, _, q, _ = _d1_d2(S, K, T, r, q, sigma)
    return S * np.exp(-q * T) * norm.pdf(d1) * np.sqrt(T)


def implied_vol(px: float, S: float, K: float, T: float, r: float, q: float,
                is_call: bool) -> float:
    """
    Implied volatility for one option using Brent's method.

    Returns ``nan`` when the price is outside the no-arbitrage bounds
    (below intrinsic value or above the upper bound), which is common for
    stale or crossed quotes in vendor data. Callers should drop those rows
    rather than force a number.
    """
    if not np.isfinite(px) or px <= 0 or T <= 0:
        return float("nan")
    df_r, df_q = np.exp(-r * T), np.exp(-q * T)
    fwd_intrinsic = max(S * df_q - K * df_r, 0.0) if is_call else max(K * df_r - S * df_q, 0.0)
    upper = S * df_q if is_call else K * df_r
    if px <= fwd_intrinsic + 1e-10 or px >= upper:
        return float("nan")

    def objective(sig: float) -> float:
        return float(price(S, K, T, r, q, sig, is_call)) - px

    try:
        return float(brentq(objective, _MIN_VOL, _MAX_VOL, xtol=1e-8, maxiter=200))
    except ValueError:
        return float("nan")


def implied_vol_array(px, S, K, T, r, q, is_call, tol: float = 1e-8,
                      max_iter: int = 120) -> np.ndarray:
    """
    Vectorised implied volatility for a whole chain at once.

    Safeguarded Newton: each option keeps a [lo, hi] bracket; a Newton step
    that would leave the bracket (or stall on tiny vega deep in the wings) is
    replaced by bisection. This converges in a handful of iterations for
    normal quotes and never diverges, and it is ~100x faster than calling
    :func:`implied_vol` row by row. Out-of-bounds prices return ``nan``.
    """
    px, S, K, T, r, q, is_call = np.broadcast_arrays(
        *(np.asarray(x, dtype=float) for x in (px, S, K, T, r, q, is_call)))
    call = is_call.astype(bool)
    shape = px.shape
    px, S, K, T, r, q, call = (a.ravel() for a in (px, S, K, T, r, q, call))
    df_r, df_q = np.exp(-r * T), np.exp(-q * T)
    intrinsic = np.where(call, np.maximum(S * df_q - K * df_r, 0), np.maximum(K * df_r - S * df_q, 0))
    upper = np.where(call, S * df_q, K * df_r)
    valid = np.isfinite(px) & (px > intrinsic + 1e-10) & (px < upper) & (T > 0)

    lo = np.full(px.shape, _MIN_VOL)
    hi = np.full(px.shape, _MAX_VOL)
    sig = np.full(px.shape, 0.3)
    for _ in range(max_iter):
        diff = price(S, K, T, r, q, sig, call) - px
        done = (np.abs(diff) < 1e-12) | ((hi - lo) < tol)
        if np.all(done | ~valid):
            break
        hi = np.where(diff > 0, sig, hi)
        lo = np.where(diff <= 0, sig, lo)
        v = vega(S, K, T, r, q, sig)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            newton = sig - diff / v
        use_newton = np.isfinite(newton) & (newton > lo) & (newton < hi) & (v > 1e-10)
        sig = np.where(done, sig, np.where(use_newton, newton, 0.5 * (lo + hi)))
    out = np.where(valid, sig, np.nan)
    return out.reshape(shape)
