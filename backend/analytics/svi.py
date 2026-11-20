"""
Raw SVI volatility-smile fitting with static-arbitrage checks.

Gatheral's raw SVI parameterises total implied variance w = sigma^2 * T as a
function of log-moneyness k = ln(K / F):

    w(k) = a + b * ( rho * (k - m) + sqrt((k - m)^2 + s^2) )

Parameters: a (level), b (wing slope, >= 0), rho (skew, |rho| < 1),
m (horizontal shift) and s (ATM curvature, > 0).

Two static-arbitrage checks are provided:

* Butterfly (per expiry): Durrleman's condition g(k) >= 0, which is equivalent
  to the implied risk-neutral density being non-negative.
* Calendar (across expiries): total variance must not decrease with maturity
  at any fixed k.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
from scipy.optimize import least_squares


@dataclass
class SVIParams:
    a: float
    b: float
    rho: float
    m: float
    s: float

    def as_array(self) -> np.ndarray:
        return np.array([self.a, self.b, self.rho, self.m, self.s])

    def to_dict(self) -> dict:
        return {k: round(v, 6) for k, v in asdict(self).items()}


def total_variance(k: np.ndarray, p: SVIParams) -> np.ndarray:
    k = np.asarray(k, dtype=float)
    return p.a + p.b * (p.rho * (k - p.m) + np.sqrt((k - p.m) ** 2 + p.s**2))


def implied_vol(k: np.ndarray, T: float, p: SVIParams) -> np.ndarray:
    return np.sqrt(np.maximum(total_variance(k, p), 1e-12) / T)


def durrleman_g(k: np.ndarray, p: SVIParams) -> np.ndarray:
    """Durrleman's g(k). Negative values mean butterfly arbitrage."""
    k = np.asarray(k, dtype=float)
    x = k - p.m
    root = np.sqrt(x**2 + p.s**2)
    w = total_variance(k, p)
    w1 = p.b * (p.rho + x / root)
    w2 = p.b * p.s**2 / root**3
    w = np.maximum(w, 1e-12)
    return (1 - k * w1 / (2 * w)) ** 2 - (w1**2 / 4) * (1 / w + 0.25) + w2 / 2


@dataclass
class SVIFit:
    params: SVIParams
    rmse_vol: float
    n_points: int
    butterfly_ok: bool
    min_g: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["params"] = self.params.to_dict()
        d["rmse_vol"] = round(self.rmse_vol, 6)
        d["min_g"] = round(self.min_g, 6)
        return d


def fit_svi(k: np.ndarray, iv: np.ndarray, T: float,
            weights: np.ndarray | None = None) -> SVIFit:
    """
    Fit raw SVI to one expiry's smile by weighted least squares on total variance.

    ``weights`` (e.g. vega or 1/spread) let liquid near-the-money quotes count
    more than illiquid wings. Bounds keep the solution inside the region where
    SVI is well defined (b >= 0, |rho| < 1, s > 0, minimum variance >= 0).
    """
    k = np.asarray(k, dtype=float)
    iv = np.asarray(iv, dtype=float)
    mask = np.isfinite(k) & np.isfinite(iv) & (iv > 0)
    k, iv = k[mask], iv[mask]
    if len(k) < 5:
        raise ValueError("Need at least 5 valid quotes to fit SVI")
    w_mkt = iv**2 * T
    wts = np.ones_like(k) if weights is None else np.asarray(weights, dtype=float)[mask]
    wts = np.sqrt(np.maximum(wts, 1e-12) / np.max(wts))

    atm_w = float(np.interp(0.0, np.sort(k), w_mkt[np.argsort(k)]))
    x0 = np.array([0.5 * atm_w, 0.1, -0.3, 0.0, 0.1])
    lower = np.array([-atm_w, 1e-6, -0.999, -1.0, 1e-4])
    upper = np.array([2 * np.max(w_mkt), 5.0, 0.999, 1.0, 2.0])

    def resid(x: np.ndarray) -> np.ndarray:
        p = SVIParams(*x)
        r = wts * (total_variance(k, p) - w_mkt)
        # Soft penalty: minimum total variance a + b*s*sqrt(1-rho^2) must be >= 0.
        min_w = x[0] + x[1] * x[4] * np.sqrt(1 - x[2] ** 2)
        return np.append(r, 10.0 * min(min_w, 0.0))

    best = None
    # Several starting points: SVI is non-convex and a single start can stall.
    for rho0, m0 in ((-0.5, 0.0), (-0.2, 0.05), (0.2, -0.05)):
        start = x0.copy()
        start[2], start[3] = rho0, m0
        sol = least_squares(resid, start, bounds=(lower, upper), method="trf", max_nfev=500)
        if best is None or sol.cost < best.cost:
            best = sol

    params = SVIParams(*(float(x) for x in best.x))
    fitted_iv = implied_vol(k, T, params)
    rmse = float(np.sqrt(np.mean((fitted_iv - iv) ** 2)))
    grid = np.linspace(min(k.min(), -1.0), max(k.max(), 1.0), 401)
    g = durrleman_g(grid, params)
    return SVIFit(params=params, rmse_vol=rmse, n_points=int(len(k)),
                  butterfly_ok=bool(g.min() >= -1e-8), min_g=float(g.min()))


def calendar_arbitrage_free(fits: list[tuple[float, SVIParams]],
                            k_grid: np.ndarray | None = None) -> tuple[bool, list[dict]]:
    """
    Check that total variance is non-decreasing in maturity at every k.

    ``fits`` is a list of ``(T, params)``. Returns ``(ok, violations)`` where each
    violation names the two maturities and the worst k.
    """
    k_grid = np.linspace(-0.5, 0.5, 101) if k_grid is None else k_grid
    ordered = sorted(fits, key=lambda x: x[0])
    violations = []
    for (t1, p1), (t2, p2) in zip(ordered, ordered[1:]):
        diff = total_variance(k_grid, p2) - total_variance(k_grid, p1)
        if diff.min() < -1e-6:
            i = int(np.argmin(diff))
            violations.append({"T_near": round(t1, 4), "T_far": round(t2, 4),
                               "k": round(float(k_grid[i]), 3), "shortfall": round(float(-diff[i]), 6)})
    return (len(violations) == 0, violations)
