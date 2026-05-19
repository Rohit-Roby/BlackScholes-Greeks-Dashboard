"""
Black-Scholes Model for Options Greeks Calculation
Implements European options pricing and Greeks calculation
"""

import numpy as np
from scipy.stats import norm
from dataclasses import dataclass
from typing import Tuple


@dataclass
class GreeksResult:
    """Data class for Greeks calculation results"""
    call_price: float
    put_price: float
    delta_call: float
    delta_put: float
    gamma: float
    theta_call: float
    theta_put: float
    vega: float
    rho_call: float
    rho_put: float


class BlackScholesCalculator:
    """
    Black-Scholes options pricing and Greeks calculator

    Implements European options pricing using the Black-Scholes model
    and calculates all Greeks (Delta, Gamma, Theta, Vega, Rho)
    """

    @staticmethod
    def _calculate_d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> Tuple[float, float]:
        """
        Calculate d1 and d2 parameters for Black-Scholes formula

        Args:
            S: Current spot price
            K: Strike price
            T: Time to expiration (in years)
            r: Risk-free interest rate (annual)
            sigma: Volatility (annual)

        Returns:
            Tuple of (d1, d2)
        """
        if T <= 0:
            raise ValueError("Time to expiration must be positive")
        if sigma <= 0:
            raise ValueError("Volatility must be positive")
        if S <= 0:
            raise ValueError("Spot price must be positive")
        if K <= 0:
            raise ValueError("Strike price must be positive")

        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

        return d1, d2

    @staticmethod
    def calculate_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """
        Calculate European call option price using Black-Scholes

        Formula: C = S*N(d1) - K*e^(-rT)*N(d2)
        """
        d1, d2 = BlackScholesCalculator._calculate_d1_d2(S, K, T, r, sigma)
        call_price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        return call_price

    @staticmethod
    def calculate_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """
        Calculate European put option price using Black-Scholes

        Formula: P = K*e^(-rT)*N(-d2) - S*N(-d1)
        """
        d1, d2 = BlackScholesCalculator._calculate_d1_d2(S, K, T, r, sigma)
        put_price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        return put_price

    @staticmethod
    def calculate_delta(S: float, K: float, T: float, r: float, sigma: float, option_type: str = 'call') -> float:
        """
        Calculate Delta (sensitivity to spot price change)

        Delta measures the rate of change of option price with respect to underlying price
        Range: Call [-0, 1], Put [-1, 0]
        """
        d1, _ = BlackScholesCalculator._calculate_d1_d2(S, K, T, r, sigma)

        if option_type.lower() == 'call':
            delta = norm.cdf(d1)
        else:  # put
            delta = norm.cdf(d1) - 1

        return delta

    @staticmethod
    def calculate_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """
        Calculate Gamma (second derivative - delta sensitivity)

        Gamma measures the rate of change of delta with respect to underlying price
        Same for both calls and puts
        """
        d1, _ = BlackScholesCalculator._calculate_d1_d2(S, K, T, r, sigma)
        gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
        return gamma

    @staticmethod
    def calculate_theta(S: float, K: float, T: float, r: float, sigma: float, option_type: str = 'call') -> float:
        """
        Calculate Theta (time decay - daily)

        Theta measures the rate of change of option price with respect to time
        Returns daily theta (divide annual theta by 365)
        """
        d1, d2 = BlackScholesCalculator._calculate_d1_d2(S, K, T, r, sigma)

        term1 = -S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))

        if option_type.lower() == 'call':
            term2 = -r * K * np.exp(-r * T) * norm.cdf(d2)
            theta_annual = term1 + term2
        else:  # put
            term2 = r * K * np.exp(-r * T) * norm.cdf(-d2)
            theta_annual = term1 + term2

        # Convert to daily theta
        theta_daily = theta_annual / 365
        return theta_daily

    @staticmethod
    def calculate_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """
        Calculate Vega (sensitivity to volatility)

        Vega measures the rate of change of option price with respect to volatility
        Same for both calls and puts
        Returns per 1% change in volatility
        """
        d1, _ = BlackScholesCalculator._calculate_d1_d2(S, K, T, r, sigma)
        vega_annual = S * norm.pdf(d1) * np.sqrt(T)

        # Return vega per 1% (0.01) change in volatility
        vega = vega_annual * 0.01
        return vega

    @staticmethod
    def calculate_rho(S: float, K: float, T: float, r: float, sigma: float, option_type: str = 'call') -> float:
        """
        Calculate Rho (sensitivity to interest rate)

        Rho measures the rate of change of option price with respect to interest rate
        Returns per 1% (0.01) change in interest rate
        """
        d1, d2 = BlackScholesCalculator._calculate_d1_d2(S, K, T, r, sigma)

        if option_type.lower() == 'call':
            rho_annual = K * T * np.exp(-r * T) * norm.cdf(d2)
        else:  # put
            rho_annual = -K * T * np.exp(-r * T) * norm.cdf(-d2)

        # Return rho per 1% (0.01) change in rate
        rho = rho_annual * 0.01
        return rho

    @staticmethod
    def calculate_all_greeks(S: float, K: float, T_days: float, r: float, sigma: float) -> GreeksResult:
        """
        Calculate all Greeks for both call and put options

        Args:
            S: Current spot price
            K: Strike price
            T_days: Time to expiration in days
            r: Risk-free interest rate (annual, as decimal)
            sigma: Volatility (annual, as decimal)

        Returns:
            GreeksResult object containing all Greeks
        """
        # Convert days to years
        T = T_days / 365.0

        # Calculate option prices
        call_price = BlackScholesCalculator.calculate_call_price(S, K, T, r, sigma)
        put_price = BlackScholesCalculator.calculate_put_price(S, K, T, r, sigma)

        # Calculate deltas
        delta_call = BlackScholesCalculator.calculate_delta(S, K, T, r, sigma, 'call')
        delta_put = BlackScholesCalculator.calculate_delta(S, K, T, r, sigma, 'put')

        # Calculate gamma (same for both)
        gamma = BlackScholesCalculator.calculate_gamma(S, K, T, r, sigma)

        # Calculate thetas
        theta_call = BlackScholesCalculator.calculate_theta(S, K, T, r, sigma, 'call')
        theta_put = BlackScholesCalculator.calculate_theta(S, K, T, r, sigma, 'put')

        # Calculate vega (same for both, per 1% IV)
        vega = BlackScholesCalculator.calculate_vega(S, K, T, r, sigma)

        # Calculate rhos
        rho_call = BlackScholesCalculator.calculate_rho(S, K, T, r, sigma, 'call')
        rho_put = BlackScholesCalculator.calculate_rho(S, K, T, r, sigma, 'put')

        return GreeksResult(
            call_price=call_price,
            put_price=put_price,
            delta_call=delta_call,
            delta_put=delta_put,
            gamma=gamma,
            theta_call=theta_call,
            theta_put=theta_put,
            vega=vega,
            rho_call=rho_call,
            rho_put=rho_put
        )
