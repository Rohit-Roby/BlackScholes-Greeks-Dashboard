"""
Market-outlook routes: expected range and direction lean per symbol, the
watchlist the main page loads, and the backtest that calibrates both.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

try:
    from backend.analytics import service
    from backend.routes.analytics import ANALYSIS_LIMIT, _run, _source, _symbol
    from backend.routes.api import limiter
except ImportError:  # standalone run from backend/
    from analytics import service
    from routes.analytics import ANALYSIS_LIMIT, _run, _source, _symbol
    from routes.api import limiter

router = APIRouter(prefix="/api/outlook", tags=["outlook"])


@router.get("/watchlist")
def get_watchlist():
    """Symbols the main page loads, the data source, and today's Databento spend."""
    return service.watchlist()


@router.get("/backtest")
def get_backtest():
    """Walk-forward results of the outlook model (summary and every observation)."""
    result = service.backtest()
    if result is None:
        raise HTTPException(status_code=404, detail="No backtest has been run yet.")
    return result


@router.get("/{symbol}")
@limiter.limit(ANALYSIS_LIMIT)
def get_outlook(request: Request, symbol: str, source: Optional[str] = Query(None)):
    """Expected range per horizon, direction lean with its factors, and key GEX levels."""
    return _run(service.outlook, _symbol(symbol), _source(source))
