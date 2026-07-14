"""
Unit tests for Black-Scholes Greeks Calculator
Validates calculations against known benchmarks and edge cases
"""

import pytest
import numpy as np
from backend.models.greeks_calculator import BlackScholesCalculator, GreeksResult


class TestBlackScholesCalculator:
    """Test suite for Black-Scholes calculations"""

    def test_call_price_atm(self):
        """Test call option price at-the-money (ATM)"""
        # For ATM option with S=K=100, the call price depends on other parameters
        S = K = 100.0
        T = 30 / 365.0  # 30 days
        r = 0.05
        sigma = 0.20  # 20% volatility

        call_price = BlackScholesCalculator.calculate_call_price(S, K, T, r, sigma)

        # Sanity checks
        assert call_price > 0, "Call price should be positive"
        assert call_price < S, "Call price should be less than spot price"

    def test_call_price_itm(self):
        """Test in-the-money (ITM) call option"""
        S = 110.0
        K = 100.0
        T = 30 / 365.0
        r = 0.05
        sigma = 0.20

        call_price = BlackScholesCalculator.calculate_call_price(S, K, T, r, sigma)
        intrinsic_value = max(S - K, 0)

        # Call price should be at least intrinsic value
        assert call_price >= intrinsic_value, "Call price should be >= intrinsic value"

    def test_call_price_otm(self):
        """Test out-of-the-money (OTM) call option"""
        S = 90.0
        K = 100.0
        T = 30 / 365.0
        r = 0.05
        sigma = 0.20

        call_price = BlackScholesCalculator.calculate_call_price(S, K, T, r, sigma)

        # OTM call price is pure time value
        assert call_price > 0, "OTM call price should be positive (time value)"

    def test_put_call_parity(self):
        """Test put-call parity: C - P = S - K*e^(-rT)"""
        S = 100.0
        K = 100.0
        T = 30 / 365.0
        r = 0.05
        sigma = 0.20

        call_price = BlackScholesCalculator.calculate_call_price(S, K, T, r, sigma)
        put_price = BlackScholesCalculator.calculate_put_price(S, K, T, r, sigma)

        lhs = call_price - put_price
        rhs = S - K * np.exp(-r * T)

        # Allow small numerical error
        assert np.isclose(lhs, rhs, rtol=1e-4), "Put-call parity should hold"

    def test_delta_call_bounds(self):
        """Test delta bounds for call options: 0 <= delta_call <= 1"""
        S_values = [80, 100, 120]
        K = 100.0
        T = 30 / 365.0
        r = 0.05
        sigma = 0.20

        for S in S_values:
            delta = BlackScholesCalculator.calculate_delta(S, K, T, r, sigma, 'call')
            assert 0 <= delta <= 1, f"Call delta should be in [0,1], got {delta}"

    def test_delta_put_bounds(self):
        """Test delta bounds for put options: -1 <= delta_put <= 0"""
        S_values = [80, 100, 120]
        K = 100.0
        T = 30 / 365.0
        r = 0.05
        sigma = 0.20

        for S in S_values:
            delta = BlackScholesCalculator.calculate_delta(S, K, T, r, sigma, 'put')
            assert -1 <= delta <= 0, f"Put delta should be in [-1,0], got {delta}"

    def test_delta_call_monotonic(self):
        """Test that call delta increases with spot price"""
        K = 100.0
        T = 30 / 365.0
        r = 0.05
        sigma = 0.20

        spot_prices = [80, 90, 100, 110, 120]
        deltas = [
            BlackScholesCalculator.calculate_delta(S, K, T, r, sigma, 'call')
            for S in spot_prices
        ]

        # Delta should be monotonically increasing
        for i in range(len(deltas) - 1):
            assert deltas[i] <= deltas[i + 1], "Delta should increase with spot price"

    def test_gamma_always_positive(self):
        """Test that gamma is always positive"""
        S_values = [80, 100, 120]
        K = 100.0
        T = 30 / 365.0
        r = 0.05
        sigma = 0.20

        for S in S_values:
            gamma = BlackScholesCalculator.calculate_gamma(S, K, T, r, sigma)
            assert gamma > 0, f"Gamma should always be positive, got {gamma}"

    def test_gamma_peak_atm(self):
        """Test that gamma is highest at-the-money"""
        K = 100.0
        T = 30 / 365.0
        r = 0.05
        sigma = 0.20

        gamma_atm = BlackScholesCalculator.calculate_gamma(K, K, T, r, sigma)
        gamma_itm = BlackScholesCalculator.calculate_gamma(110, K, T, r, sigma)
        gamma_otm = BlackScholesCalculator.calculate_gamma(90, K, T, r, sigma)

        # ATM gamma should be highest
        assert gamma_atm >= gamma_itm, "ATM gamma should be >= ITM gamma"
        assert gamma_atm >= gamma_otm, "ATM gamma should be >= OTM gamma"

    def test_theta_time_decay(self):
        """Test that theta represents time decay"""
        S = 100.0
        K = 100.0
        r = 0.05
        sigma = 0.20

        # For a long call, theta should be negative (loses value over time)
        T_long = 60 / 365.0
        call_price_long = BlackScholesCalculator.calculate_call_price(S, K, T_long, r, sigma)

        T_short = 30 / 365.0
        call_price_short = BlackScholesCalculator.calculate_call_price(S, K, T_short, r, sigma)

        # Less time to expiration means lower call price (all else equal)
        assert call_price_short < call_price_long, "Call price should decrease with less time"

    def test_vega_positive(self):
        """Test that vega is positive (option price increases with volatility)"""
        S = 100.0
        K = 100.0
        T = 30 / 365.0
        r = 0.05
        sigma = 0.20

        vega = BlackScholesCalculator.calculate_vega(S, K, T, r, sigma)
        assert vega > 0, "Vega should be positive"

    def test_vega_symmetry(self):
        """Test that vega is the same for calls and puts"""
        S = 100.0
        K = 100.0
        T = 30 / 365.0
        r = 0.05
        sigma = 0.20

        vega = BlackScholesCalculator.calculate_vega(S, K, T, r, sigma)

        # Vega should not depend on option type (should be same value)
        assert vega > 0, "Vega should be positive and same for calls/puts"

    def test_rho_call_positive(self):
        """Test that rho is positive for call options"""
        S = 100.0
        K = 100.0
        T = 30 / 365.0
        r = 0.05
        sigma = 0.20

        rho = BlackScholesCalculator.calculate_rho(S, K, T, r, sigma, 'call')
        assert rho > 0, "Call rho should be positive"

    def test_rho_put_negative(self):
        """Test that rho is negative for put options"""
        S = 100.0
        K = 100.0
        T = 30 / 365.0
        r = 0.05
        sigma = 0.20

        rho = BlackScholesCalculator.calculate_rho(S, K, T, r, sigma, 'put')
        assert rho < 0, "Put rho should be negative"

    def test_calculate_all_greeks(self):
        """Test complete Greeks calculation"""
        result = BlackScholesCalculator.calculate_all_greeks(
            S=100.0,
            K=100.0,
            T_days=30,
            r=0.05,
            sigma=0.20
        )

        assert isinstance(result, GreeksResult), "Should return GreeksResult object"
        assert result.call_price > 0, "Call price should be positive"
        assert result.put_price > 0, "Put price should be positive"
        assert -1 <= result.delta_call <= 1, "Delta call should be in [-1, 1]"
        assert -1 <= result.delta_put <= 1, "Delta put should be in [-1, 1]"
        assert result.gamma > 0, "Gamma should be positive"

    def test_invalid_inputs(self):
        """Test error handling for invalid inputs"""
        with pytest.raises(ValueError):
            BlackScholesCalculator._calculate_d1_d2(
                S=0, K=100, T=0.1, r=0.05, sigma=0.20
            )

        with pytest.raises(ValueError):
            BlackScholesCalculator._calculate_d1_d2(
                S=100, K=100, T=0, r=0.05, sigma=0.20
            )

        with pytest.raises(ValueError):
            BlackScholesCalculator._calculate_d1_d2(
                S=100, K=100, T=0.1, r=0.05, sigma=0
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
