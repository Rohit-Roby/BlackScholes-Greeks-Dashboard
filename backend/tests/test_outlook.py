"""
Tests for the Databento chain source, the market outlook and its backtest.

No network and no Databento charges: the client is replaced by a fake that
serves small frames shaped like Databento's ``to_df()`` output.
"""

from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.analytics import databento_source as dbs
from backend.analytics.gex import compute_gex
from backend.analytics.outlook import (DIRECTION_SLOPE, Factor, build_outlook, combine,
                                       horizon_range, lean_label)
from backend.analytics.outlook_backtest import summarise
from backend.analytics.sources import SyntheticChainSource, realised_vol
from backend.analytics.surface import build_surface
from backend.analytics import bsm


# --------------------------------------------------------------------------- fixtures


def synthetic_outlook(symbol="SPY"):
    snap = SyntheticChainSource().snapshot(symbol)
    surface = build_surface(snap)
    gex = compute_gex(surface.chain, snap.spot, snap.rate)
    return snap, surface, gex, build_outlook(snap, surface, gex, realised_vol(snap.closes, 20))


class FakeClient:
    """Serves Databento-shaped frames for one trading day of a toy chain."""

    def __init__(self, day=date(2026, 11, 20), spot=100.0):
        self.day, self.spot = day, spot
        self.requests = []
        self.ledger = dbs.SpendLedger.__new__(dbs.SpendLedger)

    def dataset_end(self, dataset, schema=None):
        return datetime(2026, 11, 24, 14, 30, tzinfo=timezone.utc)

    def fetch(self, req):
        self.requests.append(req)
        strikes = np.arange(80, 121, 2.5)
        expiries = [date(2026, 11, 27), date(2026, 12, 18), date(2027, 1, 15)]
        rows, iid = [], 0
        for e in expiries:
            for k in strikes:
                for cls in ("C", "P"):
                    iid += 1
                    rows.append({"instrument_id": iid, "raw_symbol": f"X {e} {cls}{k}",
                                 "expiration": pd.Timestamp(e, tz="UTC"), "strike_price": float(k),
                                 "instrument_class": cls})
        defs = pd.DataFrame(rows)
        if req.schema == "definition":
            return defs
        if req.schema == "statistics":
            oi = 1000 + 5000 * np.exp(-0.5 * ((defs["strike_price"] - 110) / 3) ** 2) * (defs["instrument_class"] == "C") \
                + 5000 * np.exp(-0.5 * ((defs["strike_price"] - 90) / 3) ** 2) * (defs["instrument_class"] == "P")
            return pd.DataFrame({"instrument_id": defs["instrument_id"], "stat_type": dbs.STAT_OPEN_INTEREST,
                                 "quantity": oi.round().astype(int)})
        if req.schema == "cbbo-1m":
            T = (pd.to_datetime(defs["expiration"]).dt.date.map(lambda e: (e - self.day).days) / 365).to_numpy()
            fair = bsm.price(self.spot, defs["strike_price"].to_numpy(), T, 0.04, 0.0, 0.25,
                             (defs["instrument_class"] == "C").to_numpy())
            return pd.DataFrame({"ts_recv": pd.Timestamp("2026-11-20T20:59Z"),
                                 "instrument_id": defs["instrument_id"],
                                 "bid_px_00": np.maximum(fair - 0.05, 0.01), "ask_px_00": fair + 0.05})
        if req.schema == "ohlcv-1d":
            idx = pd.bdate_range(end=pd.Timestamp(self.day), periods=60)
            return pd.DataFrame({"ts_event": idx.tz_localize("UTC"), "close": np.linspace(95, self.spot, 60)})
        if req.schema == "ohlcv-1m":
            return pd.DataFrame({"ts_event": [pd.Timestamp("2026-11-20T20:59Z")], "close": [self.spot]})
        raise AssertionError(req.schema)


# --------------------------------------------------------------------------- databento source


def test_pick_expiries_keeps_nearest_and_monthlies():
    today = date(2026, 11, 20)
    daily = [today + pd.Timedelta(days=i) for i in range(0, 130)]
    daily = [d.date() if hasattr(d, "date") else d for d in daily]
    picked = dbs.pick_expiries(daily, today, max_expiries=3, max_days=120)
    assert picked[:3] == daily[:3]
    assert date(2026, 12, 18) in picked and date(2027, 1, 15) in picked  # third Fridays
    assert all((d - today).days <= 120 for d in picked)


def test_spend_ledger_refuses_over_budget(tmp_path):
    ledger = dbs.SpendLedger(tmp_path / "spend.json", daily_budget=1.0)
    ledger.reserve(0.6, "first")
    with pytest.raises(dbs.BudgetExceeded):
        ledger.reserve(0.5, "second")
    assert ledger.spent_today() == pytest.approx(0.6)


def test_client_caches_and_never_pays_twice(tmp_path, monkeypatch):
    calls = {"cost": 0, "get": 0}

    class Meta:
        def get_cost(self, **kw):
            calls["cost"] += 1
            return 0.25

        def get_dataset_range(self, dataset):
            return {"end": "2026-11-24T00:00:00Z", "schema": {}}

    class Data:
        def to_df(self):
            return pd.DataFrame({"x": [1, 2]})

    class TS:
        def get_range(self, **kw):
            calls["get"] += 1
            return Data()

    class Hist:
        metadata, timeseries = Meta(), TS()

    client = dbs.DatabentoClient(key="db-test", cache_dir=tmp_path, daily_budget=1.0)
    client._hist = Hist()
    req = dbs.Request("OPRA.PILLAR", "definition", ("SPY.OPT",), "parent", "2026-11-20", "2026-11-21")
    a, b = client.fetch(req), client.fetch(req)
    assert calls == {"cost": 1, "get": 1}
    assert a.equals(b)
    assert client.ledger.spent_today() == pytest.approx(0.25)


def test_client_end_is_clamped_to_schema_availability(tmp_path):
    class Meta:
        def get_dataset_range(self, dataset):
            return {"end": "2026-11-24T05:00:00Z", "schema": {"ohlcv-1d": {"end": "2026-11-24T00:00:00Z"}}}

    client = dbs.DatabentoClient(key="db-test", cache_dir=tmp_path)
    client._hist = type("H", (), {"metadata": Meta()})()
    req = dbs.Request("EQUS.MINI", "ohlcv-1d", ("SPY",), "raw_symbol", "2026-11-01", "2026-11-30")
    assert client._clamp(req).end == "2026-11-24T00:00:00"


def test_databento_snapshot_maps_to_chain_schema():
    src = dbs.DatabentoChainSource(client=FakeClient(), asof=date(2026, 11, 20))
    snap = src.snapshot("SPY")
    c = snap.chain
    assert snap.source == "databento" and snap.spot == 100.0
    assert snap.expiries == ["2026-11-27", "2026-12-18", "2027-01-15"]  # UTC dates, not shifted
    assert c["open_interest"].gt(0).all() and c["bid"].gt(0).all()
    assert set(c["is_call"]) == {True, False}
    assert snap.asof.startswith("2026-11-20T21:00")
    # The fake chain was priced at 25% vol: the surface should find it.
    surface = build_surface(snap)
    assert abs(surface.slices[0].atm_vol - 0.25) < 0.03


def test_snapshot_time_falls_back_to_previous_close_before_10am():
    src = dbs.DatabentoChainSource(client=FakeClient())  # dataset ends at 09:30 ET on Tue 24 Nov
    assert src.snapshot_time() == dbs.session_close(date(2026, 11, 23))


# --------------------------------------------------------------------------- outlook


def test_outlook_shape_and_bounds():
    _, _, _, o = synthetic_outlook()
    assert 0.5 - DIRECTION_SLOPE <= o["direction"]["p_up"] <= 0.5 + DIRECTION_SLOPE
    assert o["direction"]["p_up"] + o["direction"]["p_down"] == pytest.approx(1.0)
    d1, d5 = o["horizons"]
    assert d1["low"] < o["spot"] < d1["high"]
    assert d5["expected_move"] > d1["expected_move"]
    assert {f["key"] for f in o["factors"]} <= {"gamma_flip", "pin_momentum", "wall_room", "implied_skew"}
    assert "not investment advice" in o["disclaimer"]


def test_combine_and_lean_label():
    f = [Factor("a", "A", 0, 1.0, 0.5, ""), Factor("b", "B", 0, -1.0, 0.5, "")]
    score, p = combine(f)
    assert score == pytest.approx(0.0) and p == pytest.approx(0.5)
    assert lean_label(0.2) == "Lean up" and lean_label(-0.2) == "Lean down" and lean_label(0.05) == "Neutral"


def test_long_gamma_shrinks_and_caps_range():
    snap, surface, gex, _ = synthetic_outlook()
    sl = surface.slices[0]
    gex.regime = "positive"
    pos = horizon_range(snap.spot, sl, 1, gex)
    gex.regime = "negative"
    neg = horizon_range(snap.spot, sl, 1, gex)
    assert pos["expected_move"] < neg["expected_move"]
    gex.regime = "positive"
    gex.call_wall = snap.spot + pos["expected_move"] * 0.5
    capped = horizon_range(snap.spot, sl, 1, gex)
    assert capped["high"] == pytest.approx(gex.call_wall) and "call wall" in capped["capped_by"]


# --------------------------------------------------------------------------- backtest


def test_backtest_summary_counts():
    recs = [
        {"date": "2026-11-10", "symbol": "SPY", "up": True, "p_up": 0.55, "lean": "Lean up",
         "regime": "positive", "inside": True, "p_inside": 0.68, "move_ratio": 0.5},
        {"date": "2026-11-11", "symbol": "SPY", "up": False, "p_up": 0.55, "lean": "Lean up",
         "regime": "negative", "inside": False, "p_inside": 0.68, "move_ratio": 1.6},
        {"date": "2026-11-12", "symbol": "QQQ", "up": True, "p_up": 0.5, "lean": "Neutral",
         "regime": "negative", "inside": True, "p_inside": 0.68, "move_ratio": 0.9},
    ]
    s = summarise(recs)
    assert s["n"] == 3 and s["leaned"] == 2 and s["direction_hit_rate"] == 0.5
    assert s["range_coverage"] == pytest.approx(2 / 3, abs=1e-3)
    assert s["by_regime"]["negative"]["n"] == 2
    assert "smoke test" in s["reliability"]


# --------------------------------------------------------------------------- API


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    monkeypatch.setenv("OUTLOOK_PREFETCH", "0")
    from backend.app import app
    from backend.analytics import service
    service.cache.clear()
    return TestClient(app, base_url="http://localhost")


def test_outlook_endpoint_synthetic(client):
    r = client.get("/api/outlook/SPY", params={"source": "synthetic"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["symbol"] == "SPY" and len(body["horizons"]) == 2


def test_outlook_watchlist_without_key_falls_back(client):
    r = client.get("/api/outlook/watchlist")
    assert r.status_code == 200
    assert r.json()["source"] != "databento" and "SPY" in r.json()["symbols"]


def test_outlook_rejects_bad_symbol_and_source(client):
    assert client.get("/api/outlook/BAD$SYM").status_code == 400
    assert client.get("/api/outlook/SPY", params={"source": "nope"}).status_code == 400
