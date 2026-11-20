"""
Tests for the options-market analytics module.

The synthetic chain source plants a known dividend yield, SVI smile and
open-interest walls, so most tests check that the analytics RECOVER that
ground truth rather than just checking that they run.
"""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.analytics import bsm
from backend.analytics.forward import estimate_forward
from backend.analytics.gex import compute_gex
from backend.analytics.scanner import scan
from backend.analytics.scenarios import (Position, max_pain, probability_of_profit,
                                         risk_neutral_density, run_scenarios)
from backend.analytics.sources import SyntheticChainSource, realised_vol
from backend.analytics.surface import build_surface
from backend.analytics.svi import (SVIParams, calendar_arbitrage_free, durrleman_g, fit_svi,
                                   total_variance)
from backend.models.greeks_calculator import BlackScholesCalculator


@pytest.fixture(scope="module")
def source():
    return SyntheticChainSource()


@pytest.fixture(scope="module")
def client():
    from backend.app import app
    return TestClient(app, base_url="http://localhost")


@pytest.fixture(scope="module")
def dividend_name(source):
    """A synthetic symbol whose planted dividend yield is non-zero."""
    snap = source.snapshot("JPM")
    assert snap.truth["q"] > 0.01
    return snap


@pytest.fixture(scope="module")
def analysed(dividend_name):
    surface = build_surface(dividend_name)
    gex = compute_gex(surface.chain, dividend_name.spot, dividend_name.rate)
    return dividend_name, surface, gex


# ------------------------------------------------------------------ BSM + implied vol


class TestBSM:
    def test_matches_original_calculator_when_no_dividend(self):
        S, K, T, r, sig = 100.0, 105.0, 0.25, 0.05, 0.3
        assert bsm.price(S, K, T, r, 0.0, sig, True) == pytest.approx(
            BlackScholesCalculator.calculate_call_price(S, K, T, r, sig), rel=1e-12)
        assert bsm.gamma(S, K, T, r, 0.0, sig) == pytest.approx(
            BlackScholesCalculator.calculate_gamma(S, K, T, r, sig), rel=1e-12)

    def test_put_call_parity_with_dividend_yield(self):
        S, K, T, r, q, sig = 100.0, 95.0, 0.5, 0.04, 0.03, 0.25
        c = bsm.price(S, K, T, r, q, sig, True)
        p = bsm.price(S, K, T, r, q, sig, False)
        assert c - p == pytest.approx(S * np.exp(-q * T) - K * np.exp(-r * T), abs=1e-10)

    def test_gamma_matches_finite_difference(self):
        S, K, T, r, q, sig, h = 100.0, 100.0, 0.2, 0.03, 0.01, 0.2, 0.01
        fd = (bsm.delta(S + h, K, T, r, q, sig, True) - bsm.delta(S - h, K, T, r, q, sig, True)) / (2 * h)
        assert bsm.gamma(S, K, T, r, q, sig) == pytest.approx(fd, rel=1e-5)

    def test_vectorised_iv_round_trip(self):
        K = np.linspace(70, 130, 61)
        vol = 0.2 + 0.4 * ((K - 100) / 100) ** 2
        is_call = K >= 100
        px = bsm.price(100, K, 0.1, 0.04, 0.01, vol, is_call)
        iv = bsm.implied_vol_array(px, 100, K, 0.1, 0.04, 0.01, is_call)
        np.testing.assert_allclose(iv, vol, atol=1e-6)

    def test_iv_rejects_prices_below_intrinsic(self):
        assert np.isnan(bsm.implied_vol(1.0, 120, 100, 0.25, 0.04, 0.0, True))
        assert np.isnan(bsm.implied_vol_array(np.array([1.0]), 120, 100, 0.25, 0.04, 0.0, True)[0])

    def test_scalar_and_vector_iv_agree(self):
        px = float(bsm.price(100, 110, 0.3, 0.04, 0.02, 0.35, True))
        a = bsm.implied_vol(px, 100, 110, 0.3, 0.04, 0.02, True)
        b = bsm.implied_vol_array(np.array([px]), 100, 110, 0.3, 0.04, 0.02, True)[0]
        assert a == pytest.approx(0.35, abs=1e-7) and b == pytest.approx(0.35, abs=1e-7)


# ------------------------------------------------------------------ forward / dividend


class TestForward:
    def test_recovers_planted_dividend_yield(self, dividend_name):
        q_true = dividend_name.truth["q"]
        for expiry, grp in dividend_name.chain.groupby("expiry"):
            est = estimate_forward(grp, dividend_name.spot, dividend_name.rate)
            assert est is not None
            if est.T >= 30 / 365:  # longer expiries pin q down tightly
                assert est.implied_div_yield == pytest.approx(q_true, abs=0.003)
            assert est.r_squared > 0.999

    def test_exact_forward_from_clean_parity(self):
        S, r, q, T = 100.0, 0.05, 0.02, 0.5
        K = np.arange(85, 116, 5.0)
        c = bsm.price(S, K, T, r, q, 0.25, True)
        p = bsm.price(S, K, T, r, q, 0.25, False)
        chain = pd.DataFrame({
            "expiry": "x", "T": T, "strike": np.concatenate([K, K]),
            "is_call": [True] * len(K) + [False] * len(K),
            "bid": np.concatenate([c, p]), "ask": np.concatenate([c, p]), "last": 0.0,
        })
        est = estimate_forward(chain, S, r)
        assert est.forward == pytest.approx(S * np.exp((r - q) * T), rel=1e-9)
        assert est.discount_factor == pytest.approx(np.exp(-r * T), rel=1e-9)
        assert est.implied_div_yield == pytest.approx(q, abs=1e-9)

    def test_too_few_pairs_returns_none(self):
        chain = pd.DataFrame({"expiry": ["x"], "T": [0.1], "strike": [100.0], "is_call": [True],
                              "bid": [1.0], "ask": [1.1], "last": [1.05]})
        assert estimate_forward(chain, 100.0, 0.04) is None


# ------------------------------------------------------------------ SVI


class TestSVI:
    TRUE = SVIParams(a=0.01, b=0.08, rho=-0.5, m=0.02, s=0.12)

    def test_recovers_known_smile(self):
        T = 0.25
        k = np.linspace(-0.4, 0.3, 40)
        iv = np.sqrt(total_variance(k, self.TRUE) / T)
        fit = fit_svi(k, iv, T)
        assert fit.rmse_vol < 1e-4
        np.testing.assert_allclose(total_variance(k, fit.params), total_variance(k, self.TRUE), atol=1e-5)
        assert fit.butterfly_ok

    def test_durrleman_flags_arbitrage(self):
        # Steep wings with tiny curvature and negative level violate g(k) >= 0
        bad = SVIParams(a=-0.05, b=1.2, rho=-0.9, m=0.0, s=0.02)
        assert durrleman_g(np.linspace(-1, 1, 201), bad).min() < 0
        assert durrleman_g(np.linspace(-1, 1, 201), self.TRUE).min() >= 0

    def test_calendar_check(self):
        near = SVIParams(0.01, 0.05, -0.4, 0.0, 0.1)
        far = SVIParams(0.03, 0.07, -0.4, 0.0, 0.15)
        assert calendar_arbitrage_free([(0.1, near), (0.3, far)])[0]
        ok, viol = calendar_arbitrage_free([(0.1, far), (0.3, near)])
        assert not ok and viol

    def test_needs_minimum_points(self):
        with pytest.raises(ValueError):
            fit_svi(np.array([0.0, 0.1]), np.array([0.2, 0.21]), 0.1)


# ------------------------------------------------------------------ surface


class TestSurface:
    def test_every_slice_fits_and_passes_checks(self, analysed):
        snap, surface, _ = analysed
        assert len(surface.slices) == len(snap.expiries)
        for sl in surface.slices:
            assert sl.svi is not None
            assert sl.svi.rmse_vol < 0.01  # under 1 vol point
            assert sl.svi.butterfly_ok
        assert surface.calendar_ok

    def test_atm_vol_matches_planted_smile(self, analysed):
        snap, surface, _ = analysed
        for sl in surface.slices:
            p = SVIParams(**snap.truth["svi"][sl.expiry])
            true_atm = np.sqrt(total_variance(np.array([0.0]), p)[0] / sl.T)
            assert sl.atm_vol == pytest.approx(true_atm, abs=0.01)

    def test_surface_is_json_safe(self, analysed):
        import json
        json.dumps(analysed[1].to_dict())


# ------------------------------------------------------------------ gamma exposure


class TestGEX:
    def test_walls_found_at_planted_strikes(self, source):
        hits = 0
        symbols = ["JPM", "SPY", "AAPL", "KO", "TSLA", "MSFT"]
        for sym in symbols:
            snap = source.snapshot(sym)
            surface = build_surface(snap)
            gex = compute_gex(surface.chain, snap.spot, snap.rate)
            step = np.diff(np.sort(snap.chain["strike"].unique())).min()
            ok_call = abs(gex.call_wall - snap.truth["call_wall"]) <= step
            ok_put = abs(gex.put_wall - snap.truth["put_wall"]) <= step
            hits += int(ok_call) + int(ok_put)  # np.bool_ + np.bool_ would be a logical OR
        assert hits >= 0.8 * 2 * len(symbols)

    def test_signs_and_flip(self, analysed):
        snap, _, gex = analysed
        assert all(v >= 0 for v in gex.call_gex)
        assert all(v <= 0 for v in gex.put_gex)
        assert gex.call_wall > gex.put_wall
        if gex.gamma_flip is not None:
            lo, hi = gex.profile_spots[0], gex.profile_spots[-1]
            assert lo <= gex.gamma_flip <= hi

    def test_gex_scales_linearly_with_open_interest(self, analysed):
        snap, surface, gex = analysed
        doubled = surface.chain.assign(open_interest=surface.chain["open_interest"] * 2)
        g2 = compute_gex(doubled, snap.spot, snap.rate)
        assert g2.total_gex == pytest.approx(2 * gex.total_gex, rel=1e-9)


# ------------------------------------------------------------------ scenarios


class TestScenarios:
    def test_density_is_a_distribution_with_the_right_mean(self, analysed):
        snap, surface, _ = analysed
        sl = surface.slices[2]
        rnd = risk_neutral_density(sl, snap.spot, snap.rate)
        mass = np.trapezoid(rnd.pdf, rnd.strikes)
        mean = np.trapezoid(rnd.pdf * rnd.strikes, rnd.strikes) / mass
        assert mass == pytest.approx(1.0, abs=0.01)
        assert mean == pytest.approx(sl.forward_used, rel=0.005)  # martingale under Q

    def test_put_skew_makes_left_tail_fatter(self, analysed):
        snap, surface, _ = analysed
        sl = surface.slices[2]
        rnd = risk_neutral_density(sl, snap.spot, snap.rate)
        F, d = sl.forward_used, 0.15
        assert rnd.prob_below(F * (1 - d)) > rnd.prob_above(F * (1 + d))

    def test_straddle_breakevens_and_pop(self, analysed):
        snap, surface, _ = analysed
        sl = surface.slices[1]
        rnd = risk_neutral_density(sl, snap.spot, snap.rate)
        pos = Position("long_straddle", 200.0, sl.expiry, sl.T, call_cost=6.0, put_cost=5.0)
        assert pos.breakevens() == [189.0, 211.0]
        assert probability_of_profit(pos, rnd) == pytest.approx(
            rnd.prob_below(189.0) + rnd.prob_above(211.0))

    @pytest.mark.parametrize("strategy", ["long_call", "long_put", "long_straddle"])
    def test_run_scenarios_output(self, analysed, strategy):
        snap, surface, gex = analysed
        out = run_scenarios(surface, gex, realised_vol(snap.closes), strategy)
        pos = out["position"]
        assert 0 <= pos["probability_of_profit"] <= 1
        assert pos["max_loss"] == pos["cost_per_contract"] > 0
        grid = np.array(out["pnl_grid"]["pnl"])
        assert grid.min() >= -pos["max_loss"] - 1e-6  # long premium never loses more than paid
        assert out["scenarios"] and "risk-neutral" in out["disclaimer"]

    def test_rejects_unsupported_strategy(self, analysed):
        snap, surface, gex = analysed
        with pytest.raises(ValueError):
            run_scenarios(surface, gex, 0.2, "short_put")

    def test_max_pain_simple_case(self):
        chain = pd.DataFrame({"expiry": "x", "strike": [90.0, 100.0, 110.0] * 2,
                              "is_call": [True] * 3 + [False] * 3,
                              "open_interest": [100, 1000, 100, 100, 1000, 100]})
        assert max_pain(chain, "x") == 100.0


# ------------------------------------------------------------------ scanner + API


class TestScannerAndAPI:
    def test_scanner_ranks_descending(self, source):
        out = scan(source, ["SPY", "TSLA", "NVDA", "KO", "AMD"], top=3, sort_by="atm_iv")
        ivs = [r["atm_iv"] for r in out["results"]]
        assert len(ivs) == 3 and ivs == sorted(ivs, reverse=True)
        assert [r["rank"] for r in out["results"]] == [1, 2, 3]

    def test_scanner_rejects_bad_sort(self, source):
        with pytest.raises(ValueError):
            scan(source, ["SPY"], sort_by="vibes")

    def test_api_endpoints(self, client):
        assert client.get("/api/analytics/meta").status_code == 200
        r = client.get("/api/analytics/scanner", params={"source": "synthetic", "top": 3, "symbols": "SPY,TSLA,KO"})
        assert r.status_code == 200 and len(r.json()["results"]) == 3
        a = client.get("/api/analytics/TSLA", params={"source": "synthetic"}).json()
        assert {"surface", "gex", "expiries", "strikes"} <= a.keys()
        s = client.get("/api/analytics/TSLA/scenarios",
                       params={"source": "synthetic", "strategy": "long_put", "expiry": a["expiries"][1]})
        assert s.status_code == 200 and s.json()["expiry"] == a["expiries"][1]

    def test_api_validation(self, client):
        assert client.get("/api/analytics/BAD$SYM", params={"source": "synthetic"}).status_code == 400
        assert client.get("/api/analytics/TSLA", params={"source": "bloomberg"}).status_code == 400
        assert client.get("/api/analytics/TSLA/scenarios",
                          params={"source": "synthetic", "strategy": "iron_condor"}).status_code == 400


# ------------------------------------------------------------------ Yahoo adapter (mocked, no network)


def test_yahoo_source_maps_yfinance_schema(monkeypatch):
    """Feeds the adapter yfinance-shaped frames and checks the tidy chain it produces."""
    import sys
    import types
    from datetime import date, timedelta
    from backend.analytics.sources import CHAIN_COLUMNS, YahooChainSource

    exp_near = (date.today() + timedelta(days=10)).isoformat()
    exp_far = (date.today() + timedelta(days=400)).isoformat()  # beyond max_days, must be dropped

    def leg(strikes):
        return pd.DataFrame({"contractSymbol": [f"X{k}" for k in strikes], "strike": strikes,
                             "lastPrice": [1.0] * len(strikes), "bid": [0.9, None, 0.8],
                             "ask": [1.1, 1.2, None], "volume": [10, None, 5],
                             "openInterest": [100, 50, None], "impliedVolatility": [0.3, 0.31, 0.32]})

    class FakeTicker:
        options = (exp_near, exp_far)

        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period="6mo"):
            idx = pd.bdate_range(end=pd.Timestamp.today(), periods=60)
            return pd.DataFrame({"Close": np.linspace(90, 100, 60)}, index=idx)

        def option_chain(self, expiry):
            return types.SimpleNamespace(calls=leg([95.0, 100.0, 105.0]), puts=leg([95.0, 100.0, 105.0]))

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=FakeTicker))
    snap = YahooChainSource(rate=0.04).snapshot("TEST")
    assert snap.spot == pytest.approx(100.0)
    assert list(snap.chain.columns) == CHAIN_COLUMNS
    assert snap.expiries == [exp_near]
    assert len(snap.chain) == 6 and snap.chain["is_call"].sum() == 3
    assert snap.chain["bid"].isna().sum() == 0 and snap.chain["open_interest"].isna().sum() == 0
    assert snap.chain["T"].iloc[0] == pytest.approx(10.5 / 365)
