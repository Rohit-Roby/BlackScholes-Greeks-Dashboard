/**
 * Main Application Logic for Options Greeks Calculator
 */

class GreeksCalculatorApp {
    constructor() {
        this.currentGreeks = null;
        this.calculationHistory = [];
        this.isDarkMode = localStorage.getItem('darkMode') === 'true';
        this.init();
    }

    /**
     * Initialize the application
     */
    init() {
        this.setupEventListeners();
        this.setupSliders();
        this.setupTabs();
        this.applyTheme();
        this.loadHistory();
        
        // Health check
        this.checkBackendHealth();
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Calculate button
        document.getElementById('calculateButton').addEventListener('click', () => {
            this.calculateGreeks();
        });

        // Fetch market data button
        document.getElementById('fetchButton').addEventListener('click', () => {
            this.fetchMarketData();
        });

        // Theme toggle
        document.getElementById('themeToggle').addEventListener('click', () => {
            this.toggleTheme();
        });

        // Enter key on inputs
        document.getElementById('spotPrice').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.calculateGreeks();
        });

        // Allow manual input sync with sliders
        document.getElementById('spotPrice').addEventListener('change', (e) => {
            document.getElementById('spotPriceSlider').value = e.target.value;
            this.updateSliderValue('spotPrice');
        });

        document.getElementById('strikePrice').addEventListener('change', (e) => {
            document.getElementById('strikePriceSlider').value = e.target.value;
            this.updateSliderValue('strikePrice');
        });

        document.getElementById('daysToExpiration').addEventListener('change', (e) => {
            document.getElementById('daysToExpirationSlider').value = e.target.value;
            this.updateSliderValue('daysToExpiration');
        });

        document.getElementById('impliedVolatility').addEventListener('change', (e) => {
            document.getElementById('impliedVolatilitySlider').value = e.target.value;
            this.updateSliderValue('impliedVolatility');
        });

        document.getElementById('interestRate').addEventListener('change', (e) => {
            document.getElementById('interestRateSlider').value = e.target.value;
            this.updateSliderValue('interestRate');
        });
    }

    /**
     * Setup slider synchronization
     */
    setupSliders() {
        const sliderPairs = [
            { slider: 'spotPriceSlider', input: 'spotPrice', display: 'spotPriceValue', format: 'currency' },
            { slider: 'strikePriceSlider', input: 'strikePrice', display: 'strikePriceValue', format: 'currency' },
            { slider: 'daysToExpirationSlider', input: 'daysToExpiration', display: 'daysToExpirationValue', format: 'days' },
            { slider: 'impliedVolatilitySlider', input: 'impliedVolatility', display: 'impliedVolatilityValue', format: 'percent' },
            { slider: 'interestRateSlider', input: 'interestRate', display: 'interestRateValue', format: 'percent' }
        ];

        sliderPairs.forEach(pair => {
            const slider = document.getElementById(pair.slider);
            const input = document.getElementById(pair.input);
            const display = document.getElementById(pair.display);

            slider.addEventListener('input', (e) => {
                input.value = e.target.value;
                this.updateDisplayValue(display, e.target.value, pair.format);
            });

            // Initialize display values
            this.updateDisplayValue(display, input.value, pair.format);
        });
    }

    /**
     * Update display value with proper formatting
     */
    updateDisplayValue(element, value, format) {
        if (format === 'currency') {
            element.textContent = `$${parseFloat(value).toFixed(2)}`;
        } else if (format === 'percent') {
            element.textContent = `${parseFloat(value).toFixed(2)}%`;
        } else if (format === 'days') {
            element.textContent = `${Math.round(value)} days`;
        } else {
            element.textContent = parseFloat(value).toFixed(2);
        }
    }

    /**
     * Update slider value display
     */
    updateSliderValue(fieldName) {
        const displayMap = {
            spotPrice: { display: 'spotPriceValue', format: 'currency' },
            strikePrice: { display: 'strikePriceValue', format: 'currency' },
            daysToExpiration: { display: 'daysToExpirationValue', format: 'days' },
            impliedVolatility: { display: 'impliedVolatilityValue', format: 'percent' },
            interestRate: { display: 'interestRateValue', format: 'percent' }
        };

        const config = displayMap[fieldName];
        if (config) {
            const input = document.getElementById(fieldName);
            this.updateDisplayValue(
                document.getElementById(config.display),
                input.value,
                config.format
            );
        }
    }

    /**
     * Setup tab functionality
     */
    setupTabs() {
        document.querySelectorAll('.tab-button').forEach(button => {
            button.addEventListener('click', () => {
                const tabName = button.getAttribute('data-tab');
                this.switchTab(tabName);
            });
        });
    }

    /**
     * Switch active tab
     */
    switchTab(tabName) {
        // Remove active class from all buttons and panes
        document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));

        // Add active class to selected button and pane
        document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
        document.getElementById(tabName).classList.add('active');

        // Trigger visualization if needed
        if (this.currentGreeks) {
            if (tabName === 'heatmap') {
                this.visualizeGreeksHeatmap();
            } else if (tabName === 'surface') {
                this.visualizeGreeksSurface();
            } else if (tabName === 'payoff') {
                this.visualizePayoffDiagram();
            }
        }
    }

    /**
     * Fetch market data for a symbol
     */
    async fetchMarketData() {
        const symbol = document.getElementById('symbol').value.trim().toUpperCase();
        if (!symbol) {
            this.showStatus('Please enter a symbol', 'error');
            return;
        }

        const statusElement = document.getElementById('symbolStatus');
        statusElement.textContent = 'Fetching...';
        statusElement.className = 'status-message loading';

        try {
            const data = await api.getMarketData(symbol);
            
            // Update inputs with fetched data
            document.getElementById('spotPrice').value = data.current_price;
            document.getElementById('spotPriceSlider').value = data.current_price;
            this.updateDisplayValue(
                document.getElementById('spotPriceValue'),
                data.current_price,
                'currency'
            );

            // Set implied volatility to historical volatility
            const iv = (data.historical_volatility * 100);
            document.getElementById('impliedVolatility').value = iv;
            document.getElementById('impliedVolatilitySlider').value = iv;
            this.updateDisplayValue(
                document.getElementById('impliedVolatilityValue'),
                iv,
                'percent'
            );

            statusElement.textContent = `✓ Fetched ${symbol}: $${data.current_price.toFixed(2)}`;
            statusElement.className = 'status-message success';
        } catch (error) {
            statusElement.textContent = `✗ ${error.message}`;
            statusElement.className = 'status-message error';
        }
    }

    /**
     * Calculate Greeks
     */
    async calculateGreeks() {
        const params = this.getInputParameters();
        
        // Validation
        if (!this.validateParameters(params)) {
            return;
        }

        const button = document.getElementById('calculateButton');
        button.disabled = true;
        button.textContent = 'Calculating...';

        try {
            const result = await api.calculateGreeks(params);
            this.currentGreeks = result;
            
            // Display results
            this.displayGreeksCards(result);
            this.addToHistory(params, result);
            
            // Display initial visualization
            setTimeout(() => this.visualizeGreeksHeatmap(), 100);
        } catch (error) {
            this.showStatus(`Error: ${error.message}`, 'error');
        } finally {
            button.disabled = false;
            button.textContent = 'Calculate Greeks';
        }
    }

    /**
     * Get input parameters
     */
    getInputParameters() {
        return {
            spotPrice: parseFloat(document.getElementById('spotPrice').value),
            strikePrice: parseFloat(document.getElementById('strikePrice').value),
            daysToExpiration: parseFloat(document.getElementById('daysToExpiration').value),
            interestRate: parseFloat(document.getElementById('interestRate').value),
            impliedVolatility: parseFloat(document.getElementById('impliedVolatility').value),
            optionType: 'call'
        };
    }

    /**
     * Validate parameters
     */
    validateParameters(params) {
        if (params.spotPrice <= 0 || params.strikePrice <= 0 || params.daysToExpiration <= 0) {
            this.showStatus('All prices and days must be positive', 'error');
            return false;
        }
        if (params.impliedVolatility <= 0 || params.impliedVolatility > 300) {
            this.showStatus('Implied volatility must be between 0% and 300%', 'error');
            return false;
        }
        if (params.interestRate < 0 || params.interestRate > 20) {
            this.showStatus('Interest rate must be between 0% and 20%', 'error');
            return false;
        }
        return true;
    }

    /**
     * Display Greeks as cards
     */
    displayGreeksCards(greeks) {
        const cardsContainer = document.getElementById('greeksCards');
        
        const cards = [
            { title: 'Call Price', value: greeks.call_price, label: '$', type: 'price' },
            { title: 'Put Price', value: greeks.put_price, label: '$', type: 'price' },
            { title: 'Delta (Call)', value: greeks.delta_call, label: '', type: 'delta' },
            { title: 'Delta (Put)', value: greeks.delta_put, label: '', type: 'delta', negative: true },
            { title: 'Gamma', value: greeks.gamma, label: '', type: 'greek' },
            { title: 'Theta (Call)', value: greeks.theta_call, label: '$/day', type: 'greek' },
            { title: 'Theta (Put)', value: greeks.theta_put, label: '$/day', type: 'greek', negative: true },
            { title: 'Vega', value: greeks.vega, label: '$/1%', type: 'greek' },
            { title: 'Rho (Call)', value: greeks.rho_call, label: '/$', type: 'greek' },
            { title: 'Rho (Put)', value: greeks.rho_put, label: '/$', type: 'greek', negative: true }
        ];

        const cardsHTML = cards.map(card => {
            const isNegative = card.negative || card.value < 0;
            const cardClass = isNegative ? 'card negative' : `card ${card.type}`;
            return `
                <div class="${cardClass}">
                    <h3>${card.title}</h3>
                    <div class="value">${card.value.toFixed(4)}</div>
                    <div class="label">${card.label}</div>
                </div>
            `;
        }).join('');

        cardsContainer.innerHTML = cardsHTML;
    }

    /**
     * Visualize Greeks Heatmap
     */
    async visualizeGreeksHeatmap() {
        if (!this.currentGreeks) return;

        const params = this.getInputParameters();
        
        try {
            const surfaceData = await api.getGreeksSurface({
                ...params,
                numPoints: 25
            });

            // Prepare data for multiple plots
            const traces = [
                {
                    x: surfaceData.spot_prices,
                    y: surfaceData.delta_call,
                    name: 'Delta (Call)',
                    type: 'scatter',
                    mode: 'lines',
                    fill: 'tozeroy'
                },
                {
                    x: surfaceData.spot_prices,
                    y: surfaceData.gamma,
                    name: 'Gamma',
                    type: 'scatter',
                    mode: 'lines',
                    yaxis: 'y2'
                }
            ];

            const layout = {
                title: 'Greeks Sensitivity to Spot Price',
                xaxis: { title: 'Spot Price ($)' },
                yaxis: { title: 'Delta' },
                yaxis2: {
                    title: 'Gamma',
                    overlaying: 'y',
                    side: 'right'
                },
                hovermode: 'x unified',
                template: this.isDarkMode ? 'plotly_dark' : 'plotly'
            };

            Plotly.newPlot('heatmapChart', traces, layout, { responsive: true });
        } catch (error) {
            console.error('Error visualizing heatmap:', error);
        }
    }

    /**
     * Visualize Greeks Surface
     */
    async visualizeGreeksSurface() {
        if (!this.currentGreeks) return;

        const params = this.getInputParameters();

        try {
            const surfaceData = await api.getGreeksSurface({
                ...params,
                numPoints: 30
            });

            // Create 2D heatmap of Greeks
            const trace = {
                x: surfaceData.spot_prices,
                y: ['Delta', 'Theta', 'Vega', 'Gamma'],
                z: [
                    surfaceData.delta_call,
                    surfaceData.theta_call.map(t => t * 365), // Convert to annual
                    surfaceData.vega,
                    surfaceData.gamma
                ],
                type: 'heatmap',
                colorscale: 'Viridis'
            };

            const layout = {
                title: 'Greeks Heatmap Across Greeks',
                xaxis: { title: 'Spot Price ($)' },
                yaxis: { title: 'Greeks' },
                template: this.isDarkMode ? 'plotly_dark' : 'plotly'
            };

            Plotly.newPlot('surfaceChart', [trace], layout, { responsive: true });
        } catch (error) {
            console.error('Error visualizing surface:', error);
        }
    }

    /**
     * Visualize Payoff Diagram
     */
    async visualizePayoffDiagram() {
        if (!this.currentGreeks) return;

        const params = this.getInputParameters();
        const spotRange = [
            params.strikePrice * 0.7,
            params.strikePrice * 1.3
        ];

        const spotPrices = [];
        for (let s = spotRange[0]; s <= spotRange[1]; s += (spotRange[1] - spotRange[0]) / 50) {
            spotPrices.push(s);
        }

        // Calculate payoffs
        const callPayoff = spotPrices.map(s => Math.max(s - params.strikePrice, 0));
        const putPayoff = spotPrices.map(s => Math.max(params.strikePrice - s, 0));
        const callWithPremium = spotPrices.map(s => 
            Math.max(s - params.strikePrice, 0) - this.currentGreeks.call_price
        );
        const putWithPremium = spotPrices.map(s => 
            Math.max(params.strikePrice - s, 0) - this.currentGreeks.put_price
        );

        const traces = [
            {
                x: spotPrices,
                y: callPayoff,
                name: 'Call (Intrinsic)',
                type: 'scatter',
                mode: 'lines'
            },
            {
                x: spotPrices,
                y: callWithPremium,
                name: 'Call (P&L)',
                type: 'scatter',
                mode: 'lines'
            },
            {
                x: spotPrices,
                y: putPayoff,
                name: 'Put (Intrinsic)',
                type: 'scatter',
                mode: 'lines'
            },
            {
                x: spotPrices,
                y: putWithPremium,
                name: 'Put (P&L)',
                type: 'scatter',
                mode: 'lines'
            }
        ];

        const layout = {
            title: 'Option Payoff Diagrams',
            xaxis: { title: 'Spot Price at Expiration ($)' },
            yaxis: { title: 'Profit/Loss ($)' },
            hovermode: 'x unified',
            template: this.isDarkMode ? 'plotly_dark' : 'plotly'
        };

        Plotly.newPlot('payoffChart', traces, layout, { responsive: true });
    }

    /**
     * Add calculation to history
     */
    addToHistory(params, result) {
        const timestamp = new Date().toLocaleTimeString();
        const historyItem = {
            timestamp,
            params,
            result
        };

        this.calculationHistory.unshift(historyItem);
        if (this.calculationHistory.length > 20) {
            this.calculationHistory.pop();
        }

        this.saveHistory();
        this.updateHistoryDisplay();
    }

    /**
     * Update history display
     */
    updateHistoryDisplay() {
        const historyList = document.getElementById('historyList');

        if (this.calculationHistory.length === 0) {
            historyList.innerHTML = '<p class="empty-state">No calculations yet</p>';
            return;
        }

        const itemsHTML = this.calculationHistory.map((item, index) => {
            const params = item.params;
            return `
                <div class="history-item" onclick="app.restoreFromHistory(${index})">
                    <div><strong>${item.timestamp}</strong></div>
                    <div style="font-size: 0.8rem; opacity: 0.8;">
                        S=$${params.spotPrice} | K=$${params.strikePrice} | T=${params.daysToExpiration}d
                    </div>
                </div>
            `;
        }).join('');

        historyList.innerHTML = itemsHTML;
    }

    /**
     * Restore parameters from history
     */
    restoreFromHistory(index) {
        const item = this.calculationHistory[index];
        const params = item.params;

        document.getElementById('spotPrice').value = params.spotPrice;
        document.getElementById('spotPriceSlider').value = params.spotPrice;
        this.updateSliderValue('spotPrice');

        document.getElementById('strikePrice').value = params.strikePrice;
        document.getElementById('strikePriceSlider').value = params.strikePrice;
        this.updateSliderValue('strikePrice');

        document.getElementById('daysToExpiration').value = params.daysToExpiration;
        document.getElementById('daysToExpirationSlider').value = params.daysToExpiration;
        this.updateSliderValue('daysToExpiration');

        document.getElementById('impliedVolatility').value = params.impliedVolatility;
        document.getElementById('impliedVolatilitySlider').value = params.impliedVolatility;
        this.updateSliderValue('impliedVolatility');

        document.getElementById('interestRate').value = params.interestRate;
        document.getElementById('interestRateSlider').value = params.interestRate;
        this.updateSliderValue('interestRate');

        this.currentGreeks = item.result;
        this.displayGreeksCards(item.result);
        this.visualizeGreeksHeatmap();
    }

    /**
     * Save history to local storage
     */
    saveHistory() {
        try {
            localStorage.setItem('calculationHistory', JSON.stringify(this.calculationHistory));
        } catch (error) {
            console.warn('Could not save history to localStorage:', error);
        }
    }

    /**
     * Load history from local storage
     */
    loadHistory() {
        try {
            const saved = localStorage.getItem('calculationHistory');
            if (saved) {
                this.calculationHistory = JSON.parse(saved);
                this.updateHistoryDisplay();
            }
        } catch (error) {
            console.warn('Could not load history from localStorage:', error);
        }
    }

    /**
     * Toggle dark mode
     */
    toggleTheme() {
        this.isDarkMode = !this.isDarkMode;
        localStorage.setItem('darkMode', this.isDarkMode);
        this.applyTheme();
    }

    /**
     * Apply theme
     */
    applyTheme() {
        const button = document.getElementById('themeToggle');
        if (this.isDarkMode) {
            document.body.classList.add('dark-mode');
            button.textContent = '☀️ Light Mode';
        } else {
            document.body.classList.remove('dark-mode');
            button.textContent = '🌙 Dark Mode';
        }

        // Redraw charts if they exist
        if (this.currentGreeks) {
            const activeTab = document.querySelector('.tab-pane.active')?.id;
            if (activeTab === 'heatmap') {
                this.visualizeGreeksHeatmap();
            } else if (activeTab === 'surface') {
                this.visualizeGreeksSurface();
            } else if (activeTab === 'payoff') {
                this.visualizePayoffDiagram();
            }
        }
    }

    /**
     * Show status message
     */
    showStatus(message, type = 'info') {
        const statusElement = document.getElementById('symbolStatus');
        statusElement.textContent = message;
        statusElement.className = `status-message ${type}`;
        
        if (type === 'error') {
            setTimeout(() => {
                statusElement.textContent = '';
                statusElement.className = 'status-message';
            }, 5000);
        }
    }

    /**
     * Check backend health
     */
    async checkBackendHealth() {
        try {
            await api.healthCheck();
            console.log('✓ Backend is healthy');
        } catch (error) {
            console.error('✗ Backend health check failed:', error);
            console.warn('Make sure the FastAPI backend is running on http://localhost:8000');
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new GreeksCalculatorApp();
});
