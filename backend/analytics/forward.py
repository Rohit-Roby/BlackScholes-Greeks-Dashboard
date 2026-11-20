"""
Implied forward, discount factor and dividend from put-call parity.

For European options on the same expiry, put-call parity says

    C(K) - P(K) = DF * (F - K) = DF * F - DF * K

so regressing ``C - P`` on ``K`` across strikes gives a straight line with
slope ``-DF`` and intercept ``DF * F``. From the fitted line:

* implied forward      F = intercept / DF
* implied rate         r = -ln(DF) / T
* implied div yield    q = r - ln(F / S) / T      (using a supplied rate)
* PV of dividends      D = S - DF * F             (cash-dividend view)

Using the market's own forward instead of an assumed dividend yield matters
for equity options: if the dividend is wrong, calls and puts at the same
strike imply different volatilities and the smile looks broken.

US single-stock options are American, so early exercise can bias deep
in-the-money pairs. The fit therefore only uses strikes near the money,
where the early-exercise premium is small.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd


@dataclass
class ForwardEstimate:
    expiry: str
    T: float
    forward: float
    discount_factor: float
    implied_rate: float
    implied_div_yield: float
    pv_dividends: float
    n_pairs: int
    r_squared: float

    def to_dict(self) -> dict:
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def _mid(df: pd.DataFrame) -> pd.Series:
    mid = (df["bid"] + df["ask"]) / 2.0
    valid = (df["bid"] > 0) & (df["ask"] >= df["bid"])
    return mid.where(valid, df["last"])


def estimate_forward(chain: pd.DataFrame, spot: float, rate: float,
                     moneyness_band: float = 0.15, min_pairs: int = 3) -> ForwardEstimate | None:
    """
    Estimate the implied forward for ONE expiry.

    ``chain`` must hold a single expiry with columns
    ``expiry, T, strike, is_call, bid, ask, last``.
    Returns ``None`` if there are too few clean call/put pairs.
    """
    if chain.empty:
        return None
    T = float(chain["T"].iloc[0])
    expiry = str(chain["expiry"].iloc[0])
    df = chain.assign(mid=_mid(chain))
    df = df[np.isfinite(df["mid"]) & (df["mid"] > 0)]
    near = df[(df["strike"] / spot - 1.0).abs() <= moneyness_band]

    calls = near[near["is_call"]].set_index("strike")["mid"]
    puts = near[~near["is_call"]].set_index("strike")["mid"]
    pairs = pd.concat([calls.rename("C"), puts.rename("P")], axis=1, join="inner").dropna()
    if len(pairs) < min_pairs:
        return None

    K = pairs.index.to_numpy(dtype=float)
    y = (pairs["C"] - pairs["P"]).to_numpy(dtype=float)

    # Ordinary least squares, then one pass of outlier rejection (crossed / stale quotes).
    slope, intercept = np.polyfit(K, y, 1)
    resid = y - (slope * K + intercept)
    mad = np.median(np.abs(resid - np.median(resid))) or 1e-12
    keep = np.abs(resid) <= 5 * 1.4826 * mad
    if keep.sum() >= min_pairs and keep.sum() < len(K):
        K, y = K[keep], y[keep]
        slope, intercept = np.polyfit(K, y, 1)

    DF = -slope
    if not (0.5 < DF <= 1.05):
        # A discount factor outside this range means the quotes are unusable;
        # fall back to the supplied rate and re-estimate only the forward.
        DF = float(np.exp(-rate * T))
        intercept = float(np.mean(y + DF * K))

    F = intercept / DF
    fitted = intercept - DF * K
    ss_res = float(np.sum((y - fitted) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1e-12
    implied_rate = float(-np.log(DF) / T) if T > 0 else rate
    q = float(rate - np.log(F / spot) / T) if T > 0 else 0.0

    return ForwardEstimate(
        expiry=expiry,
        T=T,
        forward=float(F),
        discount_factor=float(DF),
        implied_rate=implied_rate,
        implied_div_yield=q,
        pv_dividends=float(spot - DF * F),
        n_pairs=int(len(K)),
        r_squared=1.0 - ss_res / ss_tot,
    )
