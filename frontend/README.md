# Options Greeks Calculator - Frontend Setup Guide

## Quick Start

### Prerequisites
- A modern web browser (Chrome, Firefox, Safari, Edge)
- FastAPI backend running on `http://localhost:8000`

### Files
- `index.html` - Main dashboard interface
- `styles.css` - Complete styling and responsive design
- `api.js` - API service layer for backend communication
- `app.js` - Main application logic

### Running the Frontend

#### Option 1: Using Python's built-in server
```bash
cd frontend
python -m http.server 8080
```
Then open http://localhost:8080 in your browser

#### Option 2: Using Node.js http-server
```bash
npm install -g http-server
cd frontend
http-server -p 8080
```

#### Option 3: Using VS Code Live Server extension
1. Install Live Server extension in VS Code
2. Right-click on `index.html`
3. Select "Open with Live Server"

### Backend Configuration

Make sure your FastAPI backend is running:
```bash
cd backend
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

**Note:** The frontend expects the backend at `http://localhost:8000/api`

If your backend is on a different host/port, edit `api.js`:
```javascript
const api = new GreeksAPI('http://your-server:port/api');
```

## Features

### 1. Interactive Parameter Input
- **Sliders & Inputs**: Synchronized dual input with visual feedback
- **Market Data Integration**: Fetch real stock prices from Yahoo Finance
- **Validation**: Real-time parameter validation with helpful error messages

### 2. Greeks Calculation
- Call and Put prices
- Delta (directional sensitivity)
- Gamma (delta sensitivity)
- Theta (time decay)
- Vega (volatility sensitivity)
- Rho (interest rate sensitivity)

### 3. Visualizations

#### Greeks Heatmap
- Shows how Delta and Gamma change with spot price
- Identifies risk zones visually

#### Greeks Surface
- 2D heatmap across all Greeks
- Color-coded intensity map

#### Payoff Diagram
- Visualizes profit/loss at different spot prices
- Includes intrinsic value and P&L with premium

### 4. Calculation History
- Automatically saves last 20 calculations
- One-click restore of previous parameters
- Persists in browser local storage

### 5. Theme Support
- Light mode (default)
- Dark mode toggle
- Preference saved in local storage

## Usage Guide

### Calculate Greeks
1. Enter parameters (spot price, strike, expiration, etc.)
2. Click "Calculate Greeks" or press Enter
3. View results in Greeks cards
4. Switch tabs to see visualizations

### Use Market Data
1. Enter stock symbol (e.g., AAPL, SPY)
2. Click "Fetch Data"
3. Spot price and volatility auto-populate
4. Adjust other parameters as needed
5. Calculate Greeks

### Interpret Results

**Delta:**
- Call: 0 to 1 (how much call price changes per $1 spot move)
- Put: -1 to 0 (negative because puts move opposite)

**Gamma:**
- Always positive
- Indicates delta sensitivity
- Higher gamma = higher risk

**Theta:**
- Daily time decay value
- Positive for long puts/calls near expiration
- Different for calls vs puts

**Vega:**
- Sensitivity to 1% volatility change
- Positive for long positions
- Higher for at-the-money options

**Rho:**
- Sensitivity per 1% interest rate change
- Calls gain value, puts lose value with higher rates

## API Endpoints Used

```
POST /api/calculate-greeks
- Calculate all Greeks for given parameters
- Input: spot_price, strike_price, days_to_expiration, interest_rate, implied_volatility

POST /api/greeks-surface
- Get Greeks across spot price range for visualization
- Additional inputs: spot_range (tuple), num_points (int)

GET /api/market-data/{symbol}
- Fetch current price and historical volatility
- Symbol: stock ticker (AAPL, SPY, etc.)

GET /api/health
- Health check endpoint
```

## Troubleshooting

### "Cannot connect to backend"
- Ensure FastAPI server is running on port 8000
- Check firewall/network settings
- Verify CORS is enabled in backend

### Market data fetch fails
- Check internet connection
- Verify stock symbol is correct
- Yahoo Finance may have rate limiting

### Charts not rendering
- Plotly.js CDN must be accessible
- Check browser console for errors
- Ensure Plotly is loaded: `window.Plotly`

### History not saving
- Check browser privacy/incognito mode
- Verify localStorage is enabled
- Check browser storage quotas

## Browser Support
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Dependencies (Frontend)
- Plotly.js (CDN) - For interactive charts
- Vanilla JavaScript (ES6+)
- No build tools required

## Performance Tips
1. Use reasonable number of points for surface visualization (default: 30)
2. Large spot price ranges may slow calculations
3. Consider reducing slider sensitivity for smoother interaction
4. Clear history occasionally if having storage issues

## Customization

### Change API Server
Edit `api.js` line 2:
```javascript
constructor(baseURL = 'http://your-server:port/api')
```

### Adjust Slider Ranges
In `index.html`, modify min/max attributes:
```html
<input type="range" min="10" max="500" ... >
```

### Modify Color Scheme
Edit CSS variables in `styles.css`:
```css
:root {
    --primary-color: #your-color;
    /* ... other colors ... */
}
```

### Add More Greeks
1. Backend must calculate them first
2. Add card in `displayGreeksCards()` method
3. Update response model in `validation.py`

## Contact & Support
For issues or feature requests, refer to the project repository.
