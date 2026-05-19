"""
Yahoo Finance market data integration service
Fetches current prices and historical volatility data
"""

import yfinance as yf
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class MarketDataService:
    """Service for fetching market data from Yahoo Finance"""

    @staticmethod
    def get_current_price(symbol: str) -> Tuple[float, str]:
        """
        Get current stock price from Yahoo Finance

        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL', 'SPY')

        Returns:
            Tuple of (current_price, timestamp)

        Raises:
            ValueError: If symbol not found or API error
        """
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='1d')

            if data.empty:
                raise ValueError(f"No data found for symbol: {symbol}")

            current_price = float(data['Close'].iloc[-1])
            timestamp = datetime.now().isoformat()

            logger.info(f"Fetched price for {symbol}: ${current_price}")
            return current_price, timestamp

        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {str(e)}")
            raise ValueError(f"Failed to fetch price for {symbol}: {str(e)}")

    @staticmethod
    def get_historical_volatility(symbol: str, days: int = 252) -> float:
        """
        Calculate historical volatility from price data

        Args:
            symbol: Stock ticker symbol
            days: Number of days to use for calculation (default: 252 trading days = 1 year)

        Returns:
            Historical volatility as decimal (0.25 = 25%)

        Raises:
            ValueError: If symbol not found or insufficient data
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days * 1.5)  # Get extra days for calculation

            ticker = yf.Ticker(symbol)
            data = ticker.history(start=start_date, end=end_date)

            if len(data) < 30:
                raise ValueError(f"Insufficient historical data for {symbol}")

            # Calculate daily returns
            prices = data['Close'].values
            returns = np.diff(np.log(prices))

            # Calculate standard deviation (annualized)
            daily_volatility = np.std(returns)
            annual_volatility = daily_volatility * np.sqrt(252)

            logger.info(f"Historical volatility for {symbol}: {annual_volatility:.4f}")
            return annual_volatility

        except Exception as e:
            logger.error(f"Error calculating volatility for {symbol}: {str(e)}")
            raise ValueError(f"Failed to calculate volatility for {symbol}: {str(e)}")

    @staticmethod
    def get_market_data(symbol: str) -> dict:
        """
        Get complete market data snapshot including price and volatility

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dictionary with current_price, volatility, and timestamp
        """
        try:
            current_price, timestamp = MarketDataService.get_current_price(symbol)
            historical_vol = MarketDataService.get_historical_volatility(symbol)

            return {
                'symbol': symbol.upper(),
                'current_price': current_price,
                'historical_volatility': historical_vol,
                'timestamp': timestamp
            }

        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {str(e)}")
            raise
