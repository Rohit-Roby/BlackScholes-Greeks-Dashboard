"""
Dealer gamma exposure (GEX), call/put walls and the gamma-flip level.

GEX per option, in dollars of delta change for a 1% move in the underlying:

    GEX = gamma * open_interest * contract_multiplier * S^2 * 0.01

Sign convention (the common "dealers long calls, short puts" assumption):
customers tend to sell calls (overwriting) and buy puts (protection), so the
dealer is long call gamma (+) and short put gamma (-). Open interest does not
reveal who is long or short, so this is an assumption, not an observation,
and the dashboard says so.

* Call wall: strike with the largest positive call GEX. Dealer hedging around
  it tends to sell rallies, so it often acts as resistance.
* Put wall: strike with the largest negative put GEX; often acts as support.
* Gamma flip: the spot level where total GEX changes sign. Above it dealers are
  net long gamma (their hedging dampens moves); below it they are net short
  gamma (their hedging amplifies moves).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import bsm

MULTIPLIER = 100


@dataclass
class GexResult:
    spot: float
    expiries_used: list[str]
    strikes: list[float]
    call_gex: list[float]
    put_gex: list[float]
    net_gex: list[float]
    total_gex: float
    call_wall: float | None
    put_wall: float | None
    gamma_flip: float | None
    regime: str
    profile_spots: list[float]
    profile_gex: list[float]

    def to_dict(self) -> dict:
        r = lambda xs, n=2: [round(float(x), n) for x in xs]  # noqa: E731
        return {
            "spot": round(self.spot, 4),
            "expiries_used": self.expiries_used,
            "strikes": r(self.strikes, 4),
            "call_gex": r(self.call_gex),
            "put_gex": r(self.put_gex),
            "net_gex": r(self.net_gex),
            "total_gex": round(self.total_gex, 2),
            "call_wall": self.call_wall,
            "put_wall": self.put_wall,
            "gamma_flip": None if self.gamma_flip is None else round(self.gamma_flip, 4),
            "regime": self.regime,
            "profile": {"spot": r(self.profile_spots, 4), "gex": r(self.profile_gex)},
            "convention": "Dealers assumed long calls (+) and short puts (-). "
                          "GEX = gamma x OI x 100 x S^2 x 1%, in $ per 1% move.",
        }


def _option_gex(chain: pd.DataFrame, S: float, r: float) -> np.ndarray:
    g = bsm.gamma(S, chain["strike"].to_numpy(float), chain["T"].to_numpy(float), r,
                  chain["q"].to_numpy(float), chain["model_iv"].to_numpy(float))
    sign = np.where(chain["is_call"].to_numpy(bool), 1.0, -1.0)
    return sign * g * chain["open_interest"].to_numpy(float) * MULTIPLIER * S**2 * 0.01


def compute_gex(chain: pd.DataFrame, spot: float, rate: float, max_days: int = 45,
                strike_band: float = 0.25, profile_band: float = 0.15,
                n_profile: int = 61) -> GexResult:
    """
    ``chain`` must be the enriched chain from :func:`surface.build_surface`
    (needs ``model_iv`` and ``q``).
    """
    c = chain[(chain["T"] * 365 <= max_days) & np.isfinite(chain["model_iv"])
              & (chain["open_interest"] > 0)].copy()
    if c.empty:  # fall back to the nearest expiry if nothing is inside the window
        first = chain["expiry"].min()
        c = chain[(chain["expiry"] == first) & np.isfinite(chain["model_iv"])].copy()

    c["gex"] = _option_gex(c, spot, rate)
    c = c[(c["strike"] / spot - 1).abs() <= strike_band]
    by_strike = c.groupby(["strike", "is_call"])["gex"].sum().unstack(fill_value=0.0)
    for col in (True, False):
        if col not in by_strike:
            by_strike[col] = 0.0
    by_strike = by_strike.sort_index()
    strikes = by_strike.index.to_numpy(float)
    call_g, put_g = by_strike[True].to_numpy(), by_strike[False].to_numpy()
    net = call_g + put_g

    call_wall = float(strikes[np.argmax(call_g)]) if call_g.max() > 0 else None
    put_wall = float(strikes[np.argmin(put_g)]) if put_g.min() < 0 else None

    # Total GEX as a function of hypothetical spot (sticky-strike vols).
    spots = np.linspace(spot * (1 - profile_band), spot * (1 + profile_band), n_profile)
    profile = np.array([_option_gex(c, s, rate).sum() for s in spots])
    flip = None
    sign_change = np.where(np.diff(np.sign(profile)) != 0)[0]
    if len(sign_change):
        # pick the crossing closest to current spot, then interpolate linearly
        i = sign_change[np.argmin(np.abs(spots[sign_change] - spot))]
        x0, x1, y0, y1 = spots[i], spots[i + 1], profile[i], profile[i + 1]
        flip = float(x0 - y0 * (x1 - x0) / (y1 - y0))

    total = float(c["gex"].sum())
    regime = "positive" if total >= 0 else "negative"
    return GexResult(spot=spot, expiries_used=sorted(c["expiry"].unique().tolist()),
                     strikes=strikes.tolist(), call_gex=call_g.tolist(), put_gex=put_g.tolist(),
                     net_gex=net.tolist(), total_gex=total, call_wall=call_wall,
                     put_wall=put_wall, gamma_flip=flip, regime=regime,
                     profile_spots=spots.tolist(), profile_gex=profile.tolist())
