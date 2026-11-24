"""
Option chains from Databento's OPRA feed (US equity and ETF options).

One snapshot is three small historical requests for the trading day, plus two
for the underlying:

* ``definition``  (OPRA.PILLAR): every listed contract with strike, expiry and type.
* ``statistics``  (OPRA.PILLAR, 10:00-12:00 UTC only): the open interest OPRA
  publishes before the open. That window holds the whole day's open-interest
  messages and costs a fraction of the full day.
* ``cbbo-1m``     (OPRA.PILLAR): consolidated best bid/offer, last 10 minutes
  before the snapshot time.
* ``ohlcv-1m`` / ``ohlcv-1d`` (EQUS.MINI): spot at the snapshot time and six
  months of daily closes for realised volatility.

Databento bills by the data downloaded, so every request is

1. priced first with the free ``metadata.get_cost`` call and refused if it
   would push the day's spend over ``DATABENTO_DAILY_BUDGET_USD``, and
2. saved to disk under ``DATABENTO_CACHE_DIR``. The same request is never
   paid for twice.

"Live" here means the latest data the historical API has (it trails the
market by a short delay); a real-time stream needs a separate licence.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .sources import CHAIN_COLUMNS, ChainSnapshot, ChainSource

logger = logging.getLogger(__name__)

NY = ZoneInfo("America/New_York")
OPRA = "OPRA.PILLAR"
EQUITIES = "EQUS.MINI"
STAT_OPEN_INTEREST = 9  # databento StatType.OPEN_INTEREST
QUOTE_WINDOW = timedelta(minutes=10)


class BudgetExceeded(ValueError):
    """Raised instead of downloading when a request would exceed the daily budget."""


def _api_key() -> str | None:
    return os.getenv("DATABENTO_API_KEY") or None


def is_configured() -> bool:
    return _api_key() is not None


# --------------------------------------------------------------------------- spend ledger


class SpendLedger:
    """Daily Databento spend, persisted next to the cache so restarts keep the count."""

    def __init__(self, path: Path, daily_budget: float):
        self.path = path
        self.daily_budget = daily_budget
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def spent_today(self) -> float:
        return float(self._load().get(date.today().isoformat(), 0.0))

    def reserve(self, cost: float, what: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, _FileLock(self.path.with_suffix(".lock")):
            data = self._load()
            today = date.today().isoformat()
            spent = float(data.get(today, 0.0))
            if spent + cost > self.daily_budget + 1e-9:
                raise BudgetExceeded(
                    f"Databento daily budget reached: ${spent:.2f} spent today, {what} would cost "
                    f"${cost:.2f}, budget ${self.daily_budget:.2f}. Raise DATABENTO_DAILY_BUDGET_USD "
                    "or try again tomorrow; cached data still loads.")
            data[today] = round(spent + cost, 6)
            self.path.write_text(json.dumps(data, indent=1))


# --------------------------------------------------------------------------- client wrapper


@dataclass(frozen=True)
class Request:
    dataset: str
    schema: str
    symbols: tuple[str, ...]
    stype_in: str
    start: str
    end: str

    def key(self) -> str:
        raw = json.dumps(self.__dict__, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def kwargs(self) -> dict:
        return {"dataset": self.dataset, "schema": self.schema, "symbols": list(self.symbols),
                "stype_in": self.stype_in, "start": self.start, "end": self.end}


class DatabentoClient:
    """Cached, budget-guarded access to ``databento.Historical``."""

    def __init__(self, key: str | None = None, cache_dir: str | Path | None = None,
                 daily_budget: float | None = None, ledger_name: str = "spend.json"):
        self.key = key or _api_key()
        if not self.key:
            raise ValueError("DATABENTO_API_KEY is not set. Add it to the project's .env file.")
        self.cache_dir = Path(cache_dir or os.getenv("DATABENTO_CACHE_DIR", "data_cache/databento"))
        budget = daily_budget if daily_budget is not None else float(
            os.getenv("DATABENTO_DAILY_BUDGET_USD", "1.50"))
        # Separate ledgers keep one-off backtests from eating the live page's daily budget.
        self.ledger = SpendLedger(self.cache_dir / ledger_name, budget)
        self._hist = None
        self._ends: dict[str, tuple[float, dict]] = {}

    @property
    def hist(self):
        if self._hist is None:
            import databento as db  # lazy: the package is optional for other sources
            self._hist = db.Historical(self.key)
        return self._hist

    def dataset_end(self, dataset: str, schema: str | None = None) -> datetime:
        """When ``dataset`` (or one of its schemas, which can end earlier) has data up to."""
        import time as _time
        hit = self._ends.get(dataset)
        if not hit or _time.time() - hit[0] >= 600:
            hit = (_time.time(), self.hist.metadata.get_dataset_range(dataset=dataset))
            self._ends[dataset] = hit
        rng = hit[1]
        end = (rng.get("schema", {}).get(schema, {}).get("end") if schema else None) or rng["end"]
        return pd.Timestamp(end).to_pydatetime()

    def _clamp(self, req: Request) -> Request:
        """Databento rejects an ``end`` past what it has: cap it at the schema's end."""
        end = pd.Timestamp(req.end)
        end = end.tz_localize("UTC") if end.tzinfo is None else end
        avail = pd.Timestamp(self.dataset_end(req.dataset, req.schema))
        if end <= avail:
            return req
        return Request(req.dataset, req.schema, req.symbols, req.stype_in, req.start,
                       avail.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S"))

    def fetch(self, req: Request) -> pd.DataFrame:
        req = self._clamp(req)
        path = self.cache_dir / req.dataset / req.schema / f"{req.key()}.parquet"
        if path.exists():
            return pd.read_parquet(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # The API runs several worker processes: a lock file makes sure only one of them
        # pays for a given request while the others wait for its cached result.
        with _FileLock(path.with_suffix(".lock")):
            if path.exists():
                return pd.read_parquet(path)
            cost = float(self.hist.metadata.get_cost(**req.kwargs()))
            if cost > 0:
                self.ledger.reserve(cost, f"{req.schema} for {','.join(req.symbols)}")
            logger.info("databento %s %s %s %s..%s cost $%.4f", req.dataset, req.schema,
                        ",".join(req.symbols), req.start, req.end, cost)
            df = self.hist.timeseries.get_range(**req.kwargs()).to_df().reset_index()
            tmp = path.with_suffix(".tmp")
            df.to_parquet(tmp, index=False)
            os.replace(tmp, path)  # atomic: readers never see a half-written file
            return df


class _FileLock:
    """Cross-process lock via an exclusively created file; stale locks expire."""

    def __init__(self, path: Path, stale_after: float = 900.0, poll: float = 0.5):
        self.path, self.stale_after, self.poll = path, stale_after, poll

    def __enter__(self):
        import time as _time
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if _time.time() - self.path.stat().st_mtime > self.stale_after:
                        self.path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                _time.sleep(self.poll)

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
        return False


# --------------------------------------------------------------------------- helpers


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def session_close(day: date) -> datetime:
    return datetime.combine(day, time(16, 0), tzinfo=NY)


def third_friday(year: int, month: int) -> date:
    d = date(year, month, 15)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def pick_expiries(expiries: list[date], today: date, max_expiries: int, max_days: int) -> list[date]:
    """The nearest ``max_expiries`` expiries plus every standard monthly within ``max_days``.

    Index ETFs list an expiry every day, so the nearest few cover only a week; the
    monthlies carry most of the open interest that forms the gamma walls.
    """
    live = sorted(e for e in set(expiries) if 0 <= (e - today).days <= max_days)
    near = live[:max_expiries]
    monthly = [e for e in live if e == third_friday(e.year, e.month)
               or e == third_friday(e.year, e.month) - timedelta(days=1)]  # Thursday on holidays
    return sorted(set(near) | set(monthly))


# --------------------------------------------------------------------------- source


class DatabentoChainSource(ChainSource):
    """OPRA option chains from Databento, as of the latest available time or a past close."""

    name = "databento"
    REFRESH_HOURS = 2

    def __init__(self, rate: float = 0.04, client: DatabentoClient | None = None,
                 asof: date | None = None):
        self.rate = rate
        self._client = client
        self.asof = asof  # None = latest available; a date = that day's close (backtests)

    @property
    def client(self) -> DatabentoClient:
        if self._client is None:
            self._client = DatabentoClient()
        return self._client

    # -- time selection ------------------------------------------------------

    def snapshot_time(self) -> datetime:
        """Latest moment with data, capped at the session close of its day."""
        if self.asof is not None:
            return session_close(self.asof)
        # Options and the underlying must come from the same moment: use whichever feed
        # ends first (equities are often only available to the previous close).
        end = min(self.client.dataset_end(OPRA),
                  self.client.dataset_end(EQUITIES, "ohlcv-1m")).astimezone(NY)
        day = end.date()
        first = datetime.combine(day, time(10, 0), tzinfo=NY)
        if day.weekday() >= 5 or end < first:
            day = (pd.Timestamp(day) - pd.offsets.BDay(1)).date()
            return session_close(day)
        at = min(end, session_close(day))
        # Snap to REFRESH_HOURS-hour buckets (10:00, 12:00, 14:00, 16:00 ET) so quotes are
        # re-downloaded at most a few times a day; every other load hits the disk cache.
        hours = (at - first).total_seconds() // 3600
        return first + timedelta(hours=hours - hours % self.REFRESH_HOURS)

    # -- pieces ----------------------------------------------------------------

    def _definitions(self, symbol: str, day: date) -> pd.DataFrame:
        req = Request(OPRA, "definition", (f"{symbol}.OPT",), "parent",
                      day.isoformat(), (day + timedelta(days=1)).isoformat())
        df = self.client.fetch(req)
        if df.empty:
            return df
        df = df[df["instrument_class"].isin(["C", "P"])]
        df = df.drop_duplicates("instrument_id", keep="last")
        return df[["instrument_id", "raw_symbol", "expiration", "strike_price", "instrument_class"]]

    def _open_interest(self, symbol: str, day: date) -> pd.Series:
        start = datetime.combine(day, time(10, 0), tzinfo=timezone.utc)
        req = Request(OPRA, "statistics", (f"{symbol}.OPT",), "parent",
                      _iso(start), _iso(start + timedelta(hours=2)))
        df = self.client.fetch(req)
        if df.empty:
            return pd.Series(dtype=float)
        oi = df[df["stat_type"] == STAT_OPEN_INTEREST]
        return oi.groupby("instrument_id")["quantity"].last().astype(float)

    def _quotes(self, symbol: str, at: datetime) -> pd.DataFrame:
        req = Request(OPRA, "cbbo-1m", (f"{symbol}.OPT",), "parent",
                      _iso(at - QUOTE_WINDOW), _iso(at))
        df = self.client.fetch(req)
        if df.empty:
            return pd.DataFrame(columns=["instrument_id", "bid", "ask"])
        last = df.sort_values("ts_recv" if "ts_recv" in df else df.columns[0]).groupby("instrument_id").last()
        return pd.DataFrame({"bid": last["bid_px_00"].astype(float),
                             "ask": last["ask_px_00"].astype(float)}).reset_index()

    def _underlying(self, symbol: str, at: datetime) -> tuple[float, pd.Series]:
        day = at.astimezone(NY).date()
        daily = self.client.fetch(Request(EQUITIES, "ohlcv-1d", (symbol,), "raw_symbol",
                                          (day - timedelta(days=200)).isoformat(),
                                          (day + timedelta(days=1)).isoformat()))
        if daily.empty:
            raise ValueError(f"No price history for {symbol} on Databento")
        tcol = "ts_event" if "ts_event" in daily else daily.columns[0]
        daily[tcol] = pd.to_datetime(daily[tcol], utc=True)
        daily = daily[daily[tcol].dt.tz_convert(NY).dt.date <= day]
        closes = pd.Series(daily["close"].astype(float).to_numpy(),
                           index=daily[tcol].dt.tz_convert(NY).dt.normalize().dt.tz_localize(None),
                           name="Close")
        minute = self.client.fetch(Request(EQUITIES, "ohlcv-1m", (symbol,), "raw_symbol",
                                           _iso(at - QUOTE_WINDOW), _iso(at)))
        spot = float(minute["close"].iloc[-1]) if not minute.empty else float(closes.iloc[-1])
        if closes.empty or closes.index[-1].date() < day:  # today's daily bar not out yet
            closes = pd.concat([closes, pd.Series([spot], index=[pd.Timestamp(day)])])
        else:
            closes.iloc[-1] = spot
        return spot, closes

    # -- public ----------------------------------------------------------------

    def snapshot(self, symbol: str, max_expiries: int = 6, max_days: int = 120) -> ChainSnapshot:
        symbol = symbol.upper()
        at = self.snapshot_time()
        day = at.astimezone(NY).date()

        defs = pd.DataFrame()
        for _ in range(5):  # step back over market holidays
            defs = self._definitions(symbol, day)
            if not defs.empty:
                break
            day = (pd.Timestamp(day) - pd.offsets.BDay(1)).date()
            at = session_close(day)
        if defs.empty:
            raise ValueError(f"Databento has no listed options for {symbol}")

        defs = defs.copy()
        # OPRA stamps expirations at midnight UTC of the expiry date: take the UTC date as-is.
        defs["expiry"] = pd.to_datetime(defs["expiration"], utc=True).dt.date
        keep = pick_expiries(defs["expiry"].tolist(), day, max_expiries, max_days)
        defs = defs[defs["expiry"].isin(keep)]
        if defs.empty:
            raise ValueError(f"No listed options for {symbol} within {max_days} days")

        with ThreadPoolExecutor(max_workers=3) as pool:  # the downloads are independent
            f_oi = pool.submit(self._open_interest, symbol, day)
            f_quotes = pool.submit(self._quotes, symbol, at)
            f_under = pool.submit(self._underlying, symbol, at)
            oi, quotes, (spot, closes) = f_oi.result(), f_quotes.result(), f_under.result()

        df = defs.merge(quotes, on="instrument_id", how="left")
        df["open_interest"] = df["instrument_id"].map(oi).fillna(0.0)
        df = df[(df["strike_price"] / spot - 1).abs() <= 0.5]  # drop far wings early

        expiry_close = df["expiry"].map(lambda e: session_close(e))
        T = (expiry_close - at).dt.total_seconds() / (365 * 86400)
        bid = df["bid"].fillna(0.0).clip(lower=0.0)
        ask = df["ask"].fillna(0.0).clip(lower=0.0)
        chain = pd.DataFrame({
            "symbol": symbol,
            "expiry": df["expiry"].map(date.isoformat),
            "T": np.maximum(T.to_numpy(float), 0.5 / 365),
            "strike": df["strike_price"].astype(float).round(4),
            "is_call": df["instrument_class"] == "C",
            "bid": bid,
            "ask": ask,
            "last": np.where((bid > 0) & (ask >= bid), (bid + ask) / 2, 0.0),
            "volume": 0.0,  # not pulled: the outlook does not use it and it costs extra
            "open_interest": df["open_interest"],
            "vendor_iv": np.nan,
        })[CHAIN_COLUMNS].sort_values(["expiry", "strike", "is_call"]).reset_index(drop=True)

        return ChainSnapshot(symbol=symbol, spot=spot, rate=self.rate,
                             asof=at.astimezone(timezone.utc).isoformat(timespec="seconds"),
                             chain=chain, closes=closes, source=self.name)
