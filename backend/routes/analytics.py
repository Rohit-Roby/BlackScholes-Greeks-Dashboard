"""
FastAPI routes for the options-market analytics module:
volatility scanner, IV surface / gamma exposure, and scenario analysis.

Endpoints are plain ``def`` (not ``async``) on purpose: the work is CPU-bound
NumPy/SciPy plus blocking vendor I/O, so FastAPI runs them in its threadpool
instead of blocking the event loop.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

try:
    from backend.analytics import service
    from backend.routes.api import limiter
except ImportError:  # standalone run from backend/
    from analytics import service
    from routes.api import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])

SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^]{1,10}$")
SCANNER_LIMIT = "10/minute"
ANALYSIS_LIMIT = "30/minute"


def _symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not SYMBOL_RE.match(s):
        raise HTTPException(status_code=400, detail="Invalid symbol. Use 1-10 letters, digits, '.', '-' or '^'.")
    return s


def _source(source: Optional[str]) -> Optional[str]:
    if source and source.lower() not in ("yahoo", "synthetic", "databento"):
        raise HTTPException(status_code=400, detail="source must be 'yahoo', 'databento' or 'synthetic'")
    return source


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except HTTPException:
        raise
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # vendor outages, network errors
        logger.error("analytics error: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail=(
            "Market data is unavailable right now. Try again shortly, or switch the data "
            "source to 'synthetic' to explore the dashboard offline."))


@router.get("/meta")
def get_meta():
    """Available data sources, scanner universe, sort keys and strategies."""
    return service.meta()


@router.get("/scanner")
@limiter.limit(SCANNER_LIMIT)
def get_scanner(request: Request,
                top: int = Query(10, ge=1, le=50),
                sort_by: str = Query("atm_iv"),
                symbols: Optional[str] = Query(None, description="Comma-separated tickers; default universe if empty"),
                source: Optional[str] = Query(None)):
    """Rank the universe and return the top N most volatile option markets."""
    universe = [_symbol(s) for s in symbols.split(",") if s.strip()] if symbols else None
    if universe and len(universe) > 50:
        raise HTTPException(status_code=400, detail="At most 50 symbols per scan")
    return _run(service.scanner, universe, top, sort_by, _source(source))


@router.get("/{symbol}")
@limiter.limit(ANALYSIS_LIMIT)
def get_analysis(request: Request, symbol: str, source: Optional[str] = Query(None)):
    """IV surface (forwards, dividends, SVI fits, arbitrage checks) and dealer gamma exposure."""
    return _run(service.analyze, _symbol(symbol), _source(source))


@router.get("/{symbol}/scenarios")
@limiter.limit(ANALYSIS_LIMIT)
def get_scenarios(request: Request, symbol: str,
                  strategy: str = Query("long_straddle"),
                  expiry: Optional[str] = Query(None),
                  strike: Optional[float] = Query(None, gt=0),
                  iv_shift: float = Query(0.0, ge=-0.5, le=0.5, description="Parallel vol shift, e.g. 0.05 = +5 vol pts"),
                  source: Optional[str] = Query(None)):
    """Probability of profit, breakevens, key levels, P&L grid and plain-language scenarios."""
    return _run(service.scenarios, _symbol(symbol), strategy, expiry, strike, iv_shift, _source(source))
