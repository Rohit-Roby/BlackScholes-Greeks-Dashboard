"""
Scenario analysis for simple long-premium structures.

This module answers "what could happen, and what would it mean for this
position?" rather than "buy now". It supports three structures only:
long call, long put and long straddle (defined risk, no stock, no naked shorts).

Probabilities come from the risk-neutral density implied by the fitted SVI
smile (Breeden-Litzenberger: the second derivative of call prices with respect
to strike). Using the smile rather than a single flat vol means put skew is
reflected: downside tails are fatter than a lognormal would suggest.

Risk-neutral probabilities are NOT forecasts. They embed the market's risk
premium (downside protection is usually overpriced), so they describe what is
priced in, not what will happen.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import bsm
from .gex import GexResult
from .surface import ExpirySlice, SurfaceResult
from .svi import implied_vol as svi_vol

STRATEGIES = ("long_call", "long_put", "long_straddle")
MULTIPLIER = 100


# --------------------------------------------------------------------------- density


@dataclass
class RiskNeutralDensity:
    strikes: np.ndarray
    cdf: np.ndarray
    pdf: np.ndarray

    def prob_below(self, x: float) -> float:
        return float(np.clip(np.interp(x, self.strikes, self.cdf, left=0.0, right=1.0), 0, 1))

    def prob_above(self, x: float) -> float:
        return 1.0 - self.prob_below(x)

    def prob_between(self, lo: float, hi: float) -> float:
        return max(0.0, self.prob_below(hi) - self.prob_below(lo))


def slice_vol(sl: ExpirySlice, strikes: np.ndarray) -> np.ndarray:
    k = np.log(np.asarray(strikes, dtype=float) / sl.forward_used)
    if sl.svi is not None:
        return svi_vol(k, sl.T, sl.svi.params)
    return np.full_like(k, sl.atm_vol, dtype=float)


def risk_neutral_density(sl: ExpirySlice, spot: float, rate: float, n: int = 2001) -> RiskNeutralDensity:
    F, T = sl.forward_used, sl.T
    width = 6 * max(sl.atm_vol, 0.05) * np.sqrt(T)
    K = np.linspace(F * np.exp(-width), F * np.exp(width), n)
    vols = slice_vol(sl, K)
    DF = np.exp(-rate * T)
    calls = bsm.price(spot, K, T, rate, sl.div_yield_used, vols, True)
    dC = np.gradient(calls, K)
    cdf = np.clip(1.0 + dC / DF, 0.0, 1.0)
    cdf = np.maximum.accumulate(cdf)  # enforce monotonicity against numerical noise
    pdf = np.gradient(cdf, K)
    return RiskNeutralDensity(strikes=K, cdf=cdf, pdf=np.maximum(pdf, 0.0))


# --------------------------------------------------------------------------- position


@dataclass
class Position:
    strategy: str
    strike: float
    expiry: str
    T: float
    call_cost: float
    put_cost: float

    @property
    def cost(self) -> float:
        return {"long_call": self.call_cost, "long_put": self.put_cost,
                "long_straddle": self.call_cost + self.put_cost}[self.strategy]

    def payoff(self, S_T: np.ndarray) -> np.ndarray:
        S_T = np.asarray(S_T, dtype=float)
        c = np.maximum(S_T - self.strike, 0.0)
        p = np.maximum(self.strike - S_T, 0.0)
        return {"long_call": c, "long_put": p, "long_straddle": c + p}[self.strategy]

    def breakevens(self) -> list[float]:
        if self.strategy == "long_call":
            return [self.strike + self.cost]
        if self.strategy == "long_put":
            return [self.strike - self.cost]
        return [self.strike - self.cost, self.strike + self.cost]


def _quote_mid(chain: pd.DataFrame, expiry: str, strike: float, is_call: bool) -> float | None:
    row = chain[(chain["expiry"] == expiry) & (chain["strike"] == strike) & (chain["is_call"] == is_call)]
    if row.empty:
        return None
    mid = float(row["mid"].iloc[0])
    return mid if np.isfinite(mid) and mid > 0 else None


def build_position(surface: SurfaceResult, strategy: str, expiry: str | None = None,
                   strike: float | None = None) -> Position:
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {STRATEGIES}")
    sl = _pick_slice(surface, expiry)
    strikes = np.sort(surface.chain.loc[surface.chain["expiry"] == sl.expiry, "strike"].unique())
    target = surface.spot if strike is None else strike
    K = float(strikes[np.argmin(np.abs(strikes - target))])
    vol = float(slice_vol(sl, np.array([K]))[0])
    model = lambda c: float(bsm.price(surface.spot, K, sl.T, surface.rate, sl.div_yield_used, vol, c))  # noqa: E731
    call = _quote_mid(surface.chain, sl.expiry, K, True) or model(True)
    put = _quote_mid(surface.chain, sl.expiry, K, False) or model(False)
    return Position(strategy=strategy, strike=K, expiry=sl.expiry, T=sl.T, call_cost=call, put_cost=put)


def _pick_slice(surface: SurfaceResult, expiry: str | None, min_days: int = 5) -> ExpirySlice:
    if expiry:
        return surface.slice_for(expiry)
    for sl in surface.slices:
        if sl.days >= min_days:
            return sl
    return surface.slices[0]


def probability_of_profit(pos: Position, rnd: RiskNeutralDensity) -> float:
    be = pos.breakevens()
    if pos.strategy == "long_call":
        return rnd.prob_above(be[0])
    if pos.strategy == "long_put":
        return rnd.prob_below(be[0])
    return rnd.prob_below(be[0]) + rnd.prob_above(be[1])


def pnl_grid(pos: Position, sl: ExpirySlice, spot: float, rate: float,
             spot_moves: np.ndarray | None = None, day_fracs=(0.0, 0.25, 0.5, 0.75, 1.0),
             iv_shift: float = 0.0) -> dict:
    """P&L per contract across spot moves (rows) and elapsed time (columns), sticky-strike vols."""
    spot_moves = np.linspace(-0.15, 0.15, 13) if spot_moves is None else spot_moves
    S = spot * (1 + spot_moves)
    vol = max(float(slice_vol(sl, np.array([pos.strike]))[0]) + iv_shift, 0.01)
    grid = []
    for frac in day_fracs:
        t_left = pos.T * (1 - frac)
        if t_left <= 1e-6:
            value = pos.payoff(S)
        else:
            c = bsm.price(S, pos.strike, t_left, rate, sl.div_yield_used, vol, True)
            p = bsm.price(S, pos.strike, t_left, rate, sl.div_yield_used, vol, False)
            value = {"long_call": c, "long_put": p, "long_straddle": c + p}[pos.strategy]
        grid.append(((value - pos.cost) * MULTIPLIER).round(2).tolist())
    days_total = pos.T * 365
    return {
        "spot_moves_pct": (spot_moves * 100).round(2).tolist(),
        "spot_levels": S.round(2).tolist(),
        "days_elapsed": [round(f * days_total, 1) for f in day_fracs],
        "pnl": np.array(grid).T.tolist(),  # rows = spot levels, cols = time
        "iv_shift": iv_shift,
    }


# --------------------------------------------------------------------------- levels & narrative


def max_pain(chain: pd.DataFrame, expiry: str) -> float | None:
    """Strike at which total intrinsic value owed to option holders is smallest."""
    c = chain[chain["expiry"] == expiry]
    if c.empty or c["open_interest"].sum() == 0:
        return None
    strikes = np.sort(c["strike"].unique())
    K, oi, call = (c[x].to_numpy() for x in ("strike", "open_interest", "is_call"))
    pain = [np.sum(oi * np.where(call, np.maximum(s - K, 0), np.maximum(K - s, 0))) for s in strikes]
    return float(strikes[int(np.argmin(pain))])


def key_levels(spot: float, sl: ExpirySlice, gex: GexResult, mp: float | None) -> list[dict]:
    em = sl.forward_used * sl.atm_vol * np.sqrt(sl.T)
    levels = [
        {"name": "Spot", "level": spot},
        {"name": "Call wall", "level": gex.call_wall},
        {"name": "Put wall", "level": gex.put_wall},
        {"name": "Gamma flip", "level": gex.gamma_flip},
        {"name": "Max pain", "level": mp},
        {"name": "+1σ expected move", "level": sl.forward_used + em},
        {"name": "-1σ expected move", "level": sl.forward_used - em},
    ]
    out = [dict(x, level=round(float(x["level"]), 2),
                distance_pct=round((float(x["level"]) / spot - 1) * 100, 2))
           for x in levels if x["level"] is not None and np.isfinite(x["level"])]
    return sorted(out, key=lambda x: -x["level"])


def _pnl_at(pos: Position, sl: ExpirySlice, S: float, rate: float, frac: float) -> float:
    t_left = pos.T * (1 - frac)
    vol = float(slice_vol(sl, np.array([pos.strike]))[0])
    if t_left <= 1e-6:
        value = float(pos.payoff(np.array([S]))[0])
    else:
        c = float(bsm.price(S, pos.strike, t_left, rate, sl.div_yield_used, vol, True))
        p = float(bsm.price(S, pos.strike, t_left, rate, sl.div_yield_used, vol, False))
        value = {"long_call": c, "long_put": p, "long_straddle": c + p}[pos.strategy]
    return round((value - pos.cost) * MULTIPLIER, 2)


def narrative(spot: float, rate: float, sl: ExpirySlice, gex: GexResult, pos: Position,
              rnd: RiskNeutralDensity, rv20: float) -> list[dict]:
    """Plain-language scenarios, each with a priced-in probability and the position's P&L."""
    out = []
    cw, pw = gex.call_wall, gex.put_wall
    em = sl.forward_used * sl.atm_vol * np.sqrt(sl.T)

    if cw and pw and pw < spot < cw:
        out.append({
            "title": "Pinned between the walls",
            "condition": f"Price stays between the put wall {pw:g} and call wall {cw:g} until expiry.",
            "probability": round(rnd.prob_between(pw, cw), 4),
            "position_pnl": _pnl_at(pos, sl, spot, rate, 1.0),
            "context": ("Dealers are net long gamma, so their hedging tends to sell rallies and "
                        "buy dips, which favours a range." if gex.regime == "positive" else
                        "Dealers are net short gamma, so a range is less stable than usual."),
        })
    if cw:
        target = max(cw, spot + em)
        out.append({
            "title": "Break above the call wall",
            "condition": f"Price finishes above {target:,.2f} (call wall or +1σ, whichever is higher).",
            "probability": round(rnd.prob_above(target), 4),
            "position_pnl": _pnl_at(pos, sl, target, rate, 1.0),
            "context": "Above the call wall, dealer hedging flips from selling to buying, which can extend a squeeze.",
        })
    if pw:
        target = min(pw, spot - em)
        out.append({
            "title": "Break below the put wall",
            "condition": f"Price finishes below {target:,.2f} (put wall or -1σ, whichever is lower).",
            "probability": round(rnd.prob_below(target), 4),
            "position_pnl": _pnl_at(pos, sl, target, rate, 1.0),
            "context": "Below the put wall dealers are typically short gamma and must sell into weakness.",
        })
    if gex.gamma_flip:
        side = "above" if spot >= gex.gamma_flip else "below"
        out.append({
            "title": "Gamma regime change",
            "condition": f"Spot is {side} the gamma flip at {gex.gamma_flip:,.2f}; a cross changes how dealer hedging behaves.",
            "probability": round(rnd.prob_below(gex.gamma_flip) if side == "above"
                                 else rnd.prob_above(gex.gamma_flip), 4),
            "position_pnl": _pnl_at(pos, sl, gex.gamma_flip, rate, 0.5),
            "context": "Probability shown is of finishing on the other side at expiry; P&L assumes the level is reached halfway to expiry.",
        })
    if np.isfinite(rv20) and rv20 > 0:
        ratio = sl.atm_vol / rv20
        rich = ratio > 1.2
        cheap = ratio < 0.85
        out.append({
            "title": "Volatility pricing",
            "condition": f"ATM implied vol {sl.atm_vol:.1%} vs 20-day realised {rv20:.1%} (ratio {ratio:.2f}).",
            "probability": None,
            "position_pnl": _pnl_at(pos, sl, spot, rate, 0.5),
            "context": ("Options look expensive relative to recent movement: long premium needs a larger "
                        "move than usual to pay off." if rich else
                        "Options look cheap relative to recent movement: long premium is favoured if "
                        "that movement continues." if cheap else
                        "Implied and realised volatility are roughly in line."),
        })
    return out


def run_scenarios(surface: SurfaceResult, gex: GexResult, rv20: float, strategy: str,
                  expiry: str | None = None, strike: float | None = None,
                  iv_shift: float = 0.0) -> dict:
    sl = _pick_slice(surface, expiry)
    pos = build_position(surface, strategy, sl.expiry, strike)
    rnd = risk_neutral_density(sl, surface.spot, surface.rate)
    pop = probability_of_profit(pos, rnd)
    mp = max_pain(surface.chain, sl.expiry)
    em = sl.forward_used * sl.atm_vol * np.sqrt(sl.T)
    # Density thinned for plotting
    step = max(1, len(rnd.strikes) // 200)
    return {
        "symbol": surface.symbol,
        "spot": round(surface.spot, 4),
        "expiry": sl.expiry,
        "days": sl.days,
        "position": {
            "strategy": pos.strategy,
            "strike": pos.strike,
            "cost_per_share": round(pos.cost, 4),
            "cost_per_contract": round(pos.cost * MULTIPLIER, 2),
            "max_loss": round(pos.cost * MULTIPLIER, 2),
            "breakevens": [round(b, 2) for b in pos.breakevens()],
            "probability_of_profit": round(pop, 4),
            "pop_at_least_50pct": bool(pop >= 0.5),
        },
        "expected_move": {"one_sigma": round(em, 2), "one_sigma_pct": round(em / surface.spot * 100, 2),
                          "atm_vol": round(sl.atm_vol, 4)},
        "key_levels": key_levels(surface.spot, sl, gex, mp),
        "scenarios": narrative(surface.spot, surface.rate, sl, gex, pos, rnd, rv20),
        "pnl_grid": pnl_grid(pos, sl, surface.spot, surface.rate, iv_shift=iv_shift),
        "density": {"strike": rnd.strikes[::step].round(3).tolist(),
                    "pdf": rnd.pdf[::step].round(6).tolist()},
        "disclaimer": ("Probabilities are risk-neutral (what the options market prices in), not forecasts. "
                       "Scenarios are for decision support only and are not trade signals."),
    }
