"""
Input validation for Options Greeks calculation parameters
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal


class GreeksCalculationRequest(BaseModel):
    """Request model for Greeks calculation"""
    spot_price: float = Field(..., gt=0, description="Current underlying asset price")
    strike_price: float = Field(..., gt=0, description="Strike price of the option")
    days_to_expiration: float = Field(..., gt=0, le=10950, description="Days until expiration (0-30 years)")
    interest_rate: float = Field(default=0.05, ge=0, le=1, description="Risk-free interest rate (0-100%)")
    implied_volatility: float = Field(..., gt=0, le=5, description="Implied volatility (0-500%)")
    option_type: Literal['call', 'put'] = Field(default='call', description="Call or Put option")

    @field_validator('interest_rate', 'implied_volatility', mode='before')
    @classmethod
    def convert_percentage_to_decimal(cls, v):
        """Convert percentage values to decimal (30% -> 0.30)"""
        if isinstance(v, str):
            v = float(v.rstrip('%'))
        # If value > 1, assume it's in percentage format
        if v > 1:
            v = v / 100
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "spot_price": 100.0,
                "strike_price": 100.0,
                "days_to_expiration": 30,
                "interest_rate": 5,
                "implied_volatility": 25,
                "option_type": "call"
            }
        }
    }


class GreeksSurfaceRequest(BaseModel):
    """Request model for Greeks surface calculation"""
    spot_price: float = Field(..., gt=0, description="Current underlying asset price")
    strike_price: float = Field(..., gt=0, description="Strike price of the option")
    days_to_expiration: float = Field(..., gt=0, le=10950, description="Days until expiration")
    interest_rate: float = Field(default=0.05, ge=0, le=1, description="Risk-free interest rate")
    implied_volatility: float = Field(..., gt=0, le=5, description="Implied volatility")
    option_type: Literal['call', 'put'] = Field(default='call', description="Call or Put option")

    # Surface parameters
    spot_range: tuple = Field(default=(0.8, 1.2), description="Spot price range as multiplier of current spot")
    num_points: int = Field(default=20, ge=5, le=100, description="Number of points for surface")

    @field_validator('interest_rate', 'implied_volatility', mode='before')
    @classmethod
    def convert_percentage_to_decimal(cls, v):
        """Convert percentage values to decimal"""
        if isinstance(v, str):
            v = float(v.rstrip('%'))
        if v > 1:
            v = v / 100
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "spot_price": 100.0,
                "strike_price": 100.0,
                "days_to_expiration": 30,
                "interest_rate": 5,
                "implied_volatility": 25,
                "option_type": "call",
                "spot_range": [0.8, 1.2],
                "num_points": 20
            }
        }
    }


class GreeksResponse(BaseModel):
    """Response model for Greeks calculation"""
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


class MarketDataResponse(BaseModel):
    """Response model for market data"""
    symbol: str
    current_price: float
    timestamp: str
    currency: str = "USD"
