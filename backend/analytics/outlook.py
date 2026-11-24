"""
Market outlook: expected range and a direction lean from options positioning.

What it does, in order:

1. **Range (the strong part).** The 1σ move for each horizon comes from the
   at-the-money implied volatility of the matching expiry. Dealer gamma then
   scales it: when dealers are long gamma their hedging sells rallies and buys
   dips, so moves tend to be smaller than implied; when they are short gamma
   their hedging chases price and moves tend to be larger. In a long-gamma
   regime the call and put walls also cap the range.

2. **Direction (the weak part).** Four transparent factors, each scored in
   [-1, 1] and weighted:

   * *Gamma flip*: spot above the flip (stabilising hedging) leans up, below it
     leans down.
   * *Pin / momentum*: long gamma pulls price toward the strike with the most
     gamma (the pin); short gamma lets the recent move run.
   * *Wall room*: more room to the call wall than to the put wall leans up.
   * *Options-implied skew*: the risk-neutral probability of finishing above
     spot, from the fitted SVI smile.

   The weighted score maps to a probability with a deliberately small slope
   (``DIRECTION_SLOPE``), so the model never claims more than about 62/38.
   The backtest (``outlook_backtest``) measures how often these leans were
   right; the page shows that next to every call.

Nothing here is a trade signal or investment advice: open interest does not
say who is long or short, so dealer positioning is an assumption.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

from .gex import GexResult
from .scenarios import key_levels, max_pain, risk_neutral_density
from .surface import ExpirySlice, SurfaceResult

TRADING_DAYS = 252
DIRECTION_SLOPE = 0.12          # P(up) = 0.5 + slope * score, score in [-1, 1]
LEAN_THRESHOLD = 0.15           # |score| below this is reported as neutral
RANGE_MULT = {"positive": 0.85, "negative": 1.15}  # realised vs implied, by gamma regime

WEIGHTS = {"gamma_flip": 0.35, "pin_momentum": 0.25, "wall_room": 0.20, "implied_skew": 0.20}

DISCLAIMER = ("Probabilities come from option prices and an assumed dealer position (open interest "
              "does not show who is long or short). They describe tendencies, not certainties, and "
              "are not investment advice or trade signals.")


@dataclass
class Factor:
    key: str
    name: str
    value: float          # raw input, for display
    score: float          # in [-1, 1], + = up
    weight: float
    explanation: str

    @property
    def contribution(self) -> float:
        return self.score * self.weight

    def to_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "value": _r(self.value, 4),
                "score": _r(self.score, 3), "weight": self.weight,
                "contribution": _r(self.contribution, 3), "explanation": self.explanation}


def _r(x, n=2):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


# --------------------------------------------------------------------------- pieces


def _slice_for_days(surface: SurfaceResult, days: int) -> ExpirySlice:
    """The first expiry at least ``days`` calendar days out (or the last one)."""
    usable = [s for s in surface.slices if np.isfinite(s.atm_vol)]
    if not usable:
        raise ValueError("No expiry with a usable implied volatility")
    return next((s for s in usable if s.days >= days), usable[-1])


def _pin_strike(gex: GexResult, spot: float, band: float) -> float | None:
    strikes, net = np.asarray(gex.strikes, float), np.asarray(gex.net_gex, float)
    near = np.abs(strikes - spot) <= band
    if not near.any():
        return None
    idx = np.flatnonzero(near)[int(np.argmax(np.abs(net[near])))]
    return float(strikes[idx])


def _returns(closes, n: int) -> float:
    c = np.asarray(closes, dtype=float)
    return float(c[-1] / c[-1 - n] - 1) if len(c) > n else 0.0


def direction_factors(spot: float, sigma_1d: float, gex: GexResult, closes,
                      rnd_p_up: float) -> list[Factor]:
    """Score each directional input. ``sigma_1d`` is the 1-day 1σ move in dollars."""
    regime = gex.regime
    factors: list[Factor] = []

    # 1. Gamma flip
    if gex.gamma_flip is not None and sigma_1d > 0:
        z = (spot - gex.gamma_flip) / sigma_1d
        side = "above" if z >= 0 else "below"
        factors.append(Factor(
            "gamma_flip", "Spot vs gamma flip", gex.gamma_flip, math.tanh(z / 2), WEIGHTS["gamma_flip"],
            f"Spot is {abs(z):.1f} daily moves {side} the gamma flip at {gex.gamma_flip:,.2f}. "
            + ("Above the flip dealer hedging tends to steady the market, usually read as supportive."
               if z >= 0 else
               "Below the flip dealer hedging tends to amplify moves, usually read as bearish.")))

    # 2. Pin (long gamma) or momentum (short gamma)
    if regime == "positive":
        pin = _pin_strike(gex, spot, 2.5 * sigma_1d)
        if pin is not None and sigma_1d > 0:
            z = (pin - spot) / sigma_1d
            factors.append(Factor(
                "pin_momentum", "Pull toward the gamma pin", pin, math.tanh(z), WEIGHTS["pin_momentum"],
                f"Dealers are long gamma, which tends to pull price toward the strike with the most "
                f"gamma, {pin:,.2f} ({_pct(pin / spot - 1)} from spot)."))
    else:
        r5 = _returns(closes, 5)
        scale = sigma_1d / spot * math.sqrt(5) if spot > 0 else 0
        z = r5 / scale if scale > 0 else 0.0
        factors.append(Factor(
            "pin_momentum", "Momentum (short gamma)", r5, math.tanh(z / 1.5), WEIGHTS["pin_momentum"],
            f"Dealers are short gamma, so their hedging tends to extend moves. The last 5 sessions "
            f"returned {_pct(r5)}, and short-gamma markets tend to keep going that way."))

    # 3. Room to the walls
    up = (gex.call_wall - spot) if gex.call_wall and gex.call_wall > spot else None
    down = (spot - gex.put_wall) if gex.put_wall and gex.put_wall < spot else None
    if up is not None and down is not None and up + down > 0:
        score = (up - down) / (up + down)
        factors.append(Factor(
            "wall_room", "Room to the walls", score, score, WEIGHTS["wall_room"],
            f"The call wall ({gex.call_wall:,.2f}) is {_pct(up / spot)} away and the put wall "
            f"({gex.put_wall:,.2f}) {_pct(-down / spot)}. "
            + ("More room above than below." if score > 0 else "More room below than above.")))
    elif gex.call_wall or gex.put_wall:
        crossed = []
        if gex.call_wall and gex.call_wall <= spot:
            crossed.append(f"above the call wall ({gex.call_wall:,.2f})")
        if gex.put_wall and gex.put_wall >= spot:
            crossed.append(f"below the put wall ({gex.put_wall:,.2f})")
        factors.append(Factor(
            "wall_room", "Room to the walls", 0.0, 0.0, WEIGHTS["wall_room"],
            f"Spot is {' and '.join(crossed) or 'outside the walls'}, so the walls give no clear "
            f"room signal; a wall that price has crossed can act on either side."))

    # 4. Options-implied skew
    if np.isfinite(rnd_p_up):
        score = float(np.clip((rnd_p_up - 0.5) * 4, -1, 1))
        factors.append(Factor(
            "implied_skew", "Options-implied odds", rnd_p_up, score, WEIGHTS["implied_skew"],
            f"Option prices imply a {rnd_p_up * 100:.0f}% chance of finishing above spot at the "
            f"front expiry (risk-neutral, from the fitted smile)."))
    return factors


def combine(factors: list[Factor]) -> tuple[float, float]:
    """Weighted score in [-1, 1] (renormalised over available factors) and P(up)."""
    w = sum(f.weight for f in factors)
    score = sum(f.contribution for f in factors) / w if w > 0 else 0.0
    score = float(np.clip(score, -1, 1))
    return score, 0.5 + DIRECTION_SLOPE * score


def lean_label(score: float) -> str:
    if score >= LEAN_THRESHOLD:
        return "Lean up"
    if score <= -LEAN_THRESHOLD:
        return "Lean down"
    return "Neutral"


def horizon_range(spot: float, sl: ExpirySlice, trading_days: int, gex: GexResult,
                  range_mult: dict | None = None) -> dict:
    mult = (range_mult or RANGE_MULT)[gex.regime]
    sigma_pct = sl.atm_vol * math.sqrt(trading_days / TRADING_DAYS)
    implied = spot * sigma_pct
    move = implied * mult
    lo, hi = spot - move, spot + move
    capped = []
    if gex.regime == "positive":  # walls hold better when dealers are long gamma
        if gex.call_wall and spot < gex.call_wall < hi:
            hi = gex.call_wall
            capped.append("call wall")
        if gex.put_wall and lo < gex.put_wall < spot:
            lo = gex.put_wall
            capped.append("put wall")
    # Probability of closing inside [lo, hi] under a normal with the regime-scaled sigma.
    p_inside = float(norm.cdf((hi - spot) / move) - norm.cdf((lo - spot) / move)) if move > 0 else 0.0
    return {"implied_move": implied, "expected_move": move, "expected_move_pct": move / spot,
            "low": lo, "high": hi, "p_inside": p_inside, "range_mult": mult,
            "capped_by": capped, "atm_iv": sl.atm_vol, "expiry_used": sl.expiry}


# --------------------------------------------------------------------------- public


def build_outlook(snap, surface: SurfaceResult, gex: GexResult, rv20: float,
                  range_mult: dict | None = None, calibration: dict | None = None) -> dict:
    spot = snap.spot
    front = _slice_for_days(surface, 1)
    week = _slice_for_days(surface, 5)
    sigma_1d = spot * front.atm_vol / math.sqrt(TRADING_DAYS)

    rnd = risk_neutral_density(front, spot, snap.rate)
    p_up_rn = rnd.prob_above(spot)
    factors = direction_factors(spot, sigma_1d, gex, snap.closes, p_up_rn)
    score, p_up = combine(factors)

    horizons = []
    for label, sl, td in (("Next session", front, 1), ("Next 5 sessions", week, 5)):
        rng = horizon_range(spot, sl, td, gex, range_mult)
        horizons.append({
            "label": label, "trading_days": td,
            **{k: (_r(v, 4) if isinstance(v, float) else v) for k, v in rng.items()},
            "p_up": _r(p_up, 4), "p_down": _r(1 - p_up, 4),
        })

    below_flip = gex.gamma_flip is not None and spot < gex.gamma_flip
    if gex.regime == "positive" and not below_flip:
        regime_text = ("Pinned / mean-reverting: dealers are long gamma, so their hedging tends to "
                       "dampen moves and hold price between the walls.")
    elif gex.regime == "positive":
        regime_text = ("Long gamma overall but spot is below the flip: moves are dampened less, and "
                       "a further drop would push dealers short gamma.")
    else:
        regime_text = ("Volatile / trend-following: dealers are short gamma, so their hedging tends "
                       "to extend moves, and the walls hold less reliably.")

    rv_ratio = front.atm_vol / rv20 if rv20 and np.isfinite(rv20) and rv20 > 0 else float("nan")
    mp = max_pain(surface.chain, week.expiry)
    return {
        "symbol": snap.symbol,
        "source": snap.source,
        "asof": snap.asof,
        "spot": _r(spot, 4),
        "direction": {"label": lean_label(score), "score": _r(score, 3), "p_up": _r(p_up, 4),
                      "p_down": _r(1 - p_up, 4), "slope": DIRECTION_SLOPE,
                      "threshold": LEAN_THRESHOLD},
        "horizons": horizons,
        "regime": {"gamma": gex.regime, "below_flip": below_flip, "text": regime_text,
                   "total_gex": _r(gex.total_gex, 0)},
        "factors": [f.to_dict() for f in factors],
        "levels": key_levels(spot, week, gex, mp),
        "vol": {"front_atm_iv": _r(front.atm_vol, 4), "week_atm_iv": _r(week.atm_vol, 4),
                "rv20": _r(rv20, 4), "iv_rv": _r(rv_ratio, 3), "skew_10": _r(week.skew_10, 4)},
        "gex_profile": {"strikes": gex.strikes, "net_gex": [round(float(x), 2) for x in gex.net_gex],
                        "call_wall": gex.call_wall, "put_wall": gex.put_wall,
                        "gamma_flip": _r(gex.gamma_flip, 4)},
        "calibration": calibration,
        "disclaimer": DISCLAIMER,
    }
