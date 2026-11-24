"""
Backtest the market outlook on Databento history.

    python -m backend.scripts.run_outlook_backtest --symbols SPY QQQ \
        --start 2026-11-09 --end 2026-11-20 --budget 6

Reads DATABENTO_API_KEY from the environment or the project's .env. Every
download is priced first and cached under backend/data_cache/databento, so a
re-run costs nothing. Writes backend/data/outlook_backtest.json, which the API
serves to the dashboard.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from backend.analytics.databento_source import (EQUITIES, NY, DatabentoChainSource, DatabentoClient,
                                                Request)
from backend.analytics.outlook_backtest import run, to_json_ready

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend" / "data" / "outlook_backtest.json"


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", nargs="+", default=["SPY", "QQQ"])
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    p.add_argument("--budget", type=float, default=6.0, help="max Databento spend today, USD")
    p.add_argument("--rate", type=float, default=0.04)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_env()
    client = DatabentoClient(cache_dir=ROOT / "backend" / "data_cache" / "databento",
                             daily_budget=args.budget, ledger_name="spend_backtest.json")
    days = [d.date() for d in pd.bdate_range(args.start, args.end)]

    closes: dict[str, pd.Series] = {}

    def next_close_for(sym: str, day: date) -> float | None:
        if sym not in closes:
            df = client.fetch(Request(EQUITIES, "ohlcv-1d", (sym,), "raw_symbol",
                                      (args.start - timedelta(days=5)).isoformat(),
                                      (args.end + timedelta(days=10)).isoformat()))
            ts = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert(NY).dt.date
            closes[sym] = pd.Series(df["close"].astype(float).to_numpy(), index=ts)
        later = closes[sym][closes[sym].index > day]
        return float(later.iloc[0]) if len(later) else None

    def snapshot_for(sym: str, day: date):
        return DatabentoChainSource(rate=args.rate, client=client, asof=day).snapshot(sym)

    result = to_json_ready(run(args.symbols, days, snapshot_for, next_close_for))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1))
    print(json.dumps(result["summary"], indent=1))
    print(f"errors: {len(result['errors'])}  spent today: ${client.ledger.spent_today():.2f}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
