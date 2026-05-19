"""
FastAPI routes for Options Greeks Calculator
Enhanced with rate limiting and comprehensive error handling
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from slowapi import Limiter
from slowapi.util import get_remote_address
import numpy as np
import logging
import time

# Support both package run (from project root) and standalone run (from backend/)
try:
    from backend.models.greeks_calculator import BlackScholesCalculator
    from backend.services.market_data import MarketDataService
    from backend.utils.validation import (
        GreeksCalculationRequest,
        GreeksSurfaceRequest,
        GreeksResponse,
        MarketDataResponse
    )
except ImportError:
    from models.greeks_calculator import BlackScholesCalculator
    from services.market_data import MarketDataService
    from utils.validation import (
        GreeksCalculationRequest,
        GreeksSurfaceRequest,
        GreeksResponse,
        MarketDataResponse
    )

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["greeks"])
limiter = Limiter(key_func=get_remote_address)


# ============================================================
# RATE LIMITS (per endpoint)
# ============================================================
CALC_GREEKS_LIMIT = "100/minute"
SURFACE_LIMIT = "50/minute"
MARKET_DATA_LIMIT = "30/minute"


@router.post("/calculate-greeks", response_model=GreeksResponse)
@limiter.limit(CALC_GREEKS_LIMIT)
async def calculate_greeks(request: Request, calculation: GreeksCalculationRequest):
    """
    Calculate options Greeks for given parameters

    Returns all Greeks: Delta, Gamma, Theta, Vega, Rho for both call and put options
    
    **Rate Limit:** 100 requests per minute per IP
    
    **Parameters:**
    - spot_price: Current asset price (e.g., 100.0)
    - strike_price: Option strike price (e.g., 100.0)
    - days_to_expiration: Days until expiration (1-365)
    - interest_rate: Risk-free rate in % (0-10)
    - implied_volatility: Annual volatility in % (0.1-200)
    - option_type: 'call' or 'put'
    """
    start_time = time.time()
    try:
        logger.info(f"Calculating Greeks: S={calculation.spot_price}, K={calculation.strike_price}")
        
        greeks_result = BlackScholesCalculator.calculate_all_greeks(
            S=calculation.spot_price,
            K=calculation.strike_price,
            T_days=calculation.days_to_expiration,
            r=calculation.interest_rate,
            sigma=calculation.implied_volatility
        )

        response = GreeksResponse(
            call_price=round(greeks_result.call_price, 4),
            put_price=round(greeks_result.put_price, 4),
            delta_call=round(greeks_result.delta_call, 4),
            delta_put=round(greeks_result.delta_put, 4),
            gamma=round(greeks_result.gamma, 6),
            theta_call=round(greeks_result.theta_call, 6),
            theta_put=round(greeks_result.theta_put, 6),
            vega=round(greeks_result.vega, 4),
            rho_call=round(greeks_result.rho_call, 4),
            rho_put=round(greeks_result.rho_put, 4)
        )
        
        elapsed = time.time() - start_time
        logger.debug(f"Greeks calculation completed in {elapsed:.3f}s")
        return response

    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid input: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Calculation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error calculating Greeks. Please check your input parameters."
        )


@router.post("/greeks-surface")
@limiter.limit(SURFACE_LIMIT)
async def get_greeks_surface(request: Request, surface_request: GreeksSurfaceRequest):
    """
    Calculate Greeks surface data across spot price range

    Useful for visualizing how Greeks change with spot price
    
    **Rate Limit:** 50 requests per minute per IP
    
    **Returns:** Greeks values across a range of spot prices for heatmap visualization
    """
    start_time = time.time()
    try:
        logger.info(f"Calculating Greeks surface: {surface_request.num_points} points")
        
        lower_bound = surface_request.spot_price * surface_request.spot_range[0]
        upper_bound = surface_request.spot_price * surface_request.spot_range[1]
        spot_prices = np.linspace(lower_bound, upper_bound, surface_request.num_points)

        surface_data = {
            'spot_prices': spot_prices.tolist(),
            'delta_call': [],
            'delta_put': [],
            'gamma': [],
            'theta_call': [],
            'theta_put': [],
            'vega': [],
            'call_prices': [],
            'put_prices': []
        }

        for spot in spot_prices:
            try:
                greeks_result = BlackScholesCalculator.calculate_all_greeks(
                    S=spot,
                    K=surface_request.strike_price,
                    T_days=surface_request.days_to_expiration,
                    r=surface_request.interest_rate,
                    sigma=surface_request.implied_volatility
                )

                surface_data['delta_call'].append(round(greeks_result.delta_call, 4))
                surface_data['delta_put'].append(round(greeks_result.delta_put, 4))
                surface_data['gamma'].append(round(greeks_result.gamma, 6))
                surface_data['theta_call'].append(round(greeks_result.theta_call, 6))
                surface_data['theta_put'].append(round(greeks_result.theta_put, 6))
                surface_data['vega'].append(round(greeks_result.vega, 4))
                surface_data['call_prices'].append(round(greeks_result.call_price, 4))
                surface_data['put_prices'].append(round(greeks_result.put_price, 4))
            except Exception as e:
                logger.error(f"Error at spot price {spot}: {str(e)}")
                raise

        elapsed = time.time() - start_time
        logger.debug(f"Greeks surface calculation completed in {elapsed:.3f}s")
        return surface_data

    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid input: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Calculation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error calculating Greeks surface. Please check your input parameters."
        )


@router.get("/market-data/{symbol}")
@limiter.limit(MARKET_DATA_LIMIT)
async def get_market_data(request: Request, symbol: str):
    """
    Get market data for a symbol (current price and historical volatility)

    Fetches real-time data from Yahoo Finance
    
    **Rate Limit:** 30 requests per minute per IP
    
    **Parameters:**
    - symbol: Stock ticker symbol (e.g., 'AAPL', 'SPY', 'TSLA')

    **Returns:**
    - symbol: The requested ticker
    - current_price: Current market price
    - historical_volatility: Annualized volatility (0-1 range)
    - timestamp: Data fetch timestamp
    """
    start_time = time.time()
    try:
        logger.info(f"Fetching market data for {symbol.upper()}")
        
        # Validate symbol format
        if not symbol or not isinstance(symbol, str) or len(symbol) > 10:
            raise ValueError("Invalid symbol format. Use 1-10 character ticker symbols.")
        
        market_data = MarketDataService.get_market_data(symbol.upper())

        response = {
            "symbol": market_data['symbol'],
            "current_price": round(market_data['current_price'], 2),
            "historical_volatility": round(market_data['historical_volatility'], 4),
            "timestamp": market_data['timestamp']
        }
        
        elapsed = time.time() - start_time
        logger.debug(f"Market data fetch for {symbol} completed in {elapsed:.3f}s")
        return response

    except ValueError as e:
        logger.warning(f"Market data validation error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid symbol: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Market data fetch error for {symbol}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=f"Could not fetch data for symbol '{symbol}'. Yahoo Finance may be unavailable. Try again in a few moments."
        )
