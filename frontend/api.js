/**
 * API Service for communicating with the backend
 */

class GreeksAPI {
    constructor(baseURL = 'http://localhost:8000/api') {
        this.baseURL = baseURL;
        this.timeout = 10000; // 10 seconds
    }

    /**
     * Make API request with error handling
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            method: options.method || 'GET',
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            timeout: this.timeout
        };

        if (options.body) {
            config.body = JSON.stringify(options.body);
        }

        try {
            const response = await fetch(url, config);
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || `HTTP Error: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`API Error: ${error.message}`);
            throw error;
        }
    }

    /**
     * Calculate Greeks for given parameters
     */
    async calculateGreeks(params) {
        return this.request('/calculate-greeks', {
            method: 'POST',
            body: {
                spot_price: params.spotPrice,
                strike_price: params.strikePrice,
                days_to_expiration: params.daysToExpiration,
                interest_rate: params.interestRate,
                implied_volatility: params.impliedVolatility,
                option_type: params.optionType || 'call'
            }
        });
    }

    /**
     * Get Greeks surface data for visualization
     */
    async getGreeksSurface(params) {
        return this.request('/greeks-surface', {
            method: 'POST',
            body: {
                spot_price: params.spotPrice,
                strike_price: params.strikePrice,
                days_to_expiration: params.daysToExpiration,
                interest_rate: params.interestRate,
                implied_volatility: params.impliedVolatility,
                option_type: params.optionType || 'call',
                spot_range: params.spotRange || [0.8, 1.2],
                num_points: params.numPoints || 30
            }
        });
    }

    /**
     * Fetch market data for a symbol
     */
    async getMarketData(symbol) {
        return this.request(`/market-data/${symbol}`, {
            method: 'GET'
        });
    }

    /**
     * Health check
     */
    async healthCheck() {
        return this.request('/health', {
            method: 'GET'
        });
    }
}

// Create global API instance
const api = new GreeksAPI();
