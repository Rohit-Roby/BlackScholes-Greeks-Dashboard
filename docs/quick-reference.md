# Quick Reference Guide

## 🚀 Quick Start (30 seconds)

### Windows
```batch
setup.bat
```
Then in two separate terminals:
```batch
# Terminal 1
cd backend && venv\Scripts\activate && python -m uvicorn app:app --port 8000

# Terminal 2  
cd frontend && python -m http.server 8080
```

### Linux/macOS
```bash
./setup.sh
```
Then in two separate terminals:
```bash
# Terminal 1
cd backend && source venv/bin/activate && python -m uvicorn app:app --port 8000

# Terminal 2
cd frontend && python -m http.server 8080
```

### Open in Browser
```
http://localhost:8080
```

---

## 📊 Understanding Greeks

| Greek | Meaning | Interpretation |
|-------|---------|-----------------|
| **Delta (Δ)** | Option price change per $1 spot move | How much profit/loss per $1 move |
| **Gamma (Γ)** | Delta change per $1 spot move | How fast delta changes (risk) |
| **Theta (Θ)** | Daily time decay | How much value lost per day |
| **Vega (ν)** | 1% volatility change impact | Exposure to volatility changes |
| **Rho (ρ)** | 1% interest rate change impact | Exposure to rate changes |

### Quick Interpretation
- **Short on time?** → High negative Theta (good for sellers)
- **Expect volatility?** → High Vega (good for long options)
- **Price swings?** → High Gamma (risky!)
- **ATM options?** → Usually highest Gamma and Vega

---

## 🎮 Dashboard Features

### Input Controls
- **Sliders**: Drag to adjust, synchronized with input fields
- **Input Fields**: Type values directly
- **Market Data**: Enter stock symbol and click "Fetch Data"
- **Dark Mode**: Toggle with button in header

### Visualizations
- **Tab 1 - Heatmap**: Delta and Gamma sensitivity
- **Tab 2 - Surface**: 2D heatmap across all Greeks
- **Tab 3 - Payoff**: Profit/loss diagram at expiration

### History
- Auto-saves last 20 calculations
- Click history item to restore
- Persists in browser (not lost on refresh)

---

## 🔌 API Quick Reference

### Health Check
```bash
curl http://localhost:8000/api/health
```

### Calculate Greeks
```bash
curl -X POST http://localhost:8000/api/calculate-greeks \
  -H "Content-Type: application/json" \
  -d '{
    "spot_price": 100,
    "strike_price": 100,
    "days_to_expiration": 30,
    "interest_rate": 5,
    "implied_volatility": 25,
    "option_type": "call"
  }'
```

### Get Market Data
```bash
curl http://localhost:8000/api/market-data/AAPL
```

### Greeks Surface
```bash
curl -X POST http://localhost:8000/api/greeks-surface \
  -H "Content-Type: application/json" \
  -d '{
    "spot_price": 100,
    "strike_price": 100,
    "days_to_expiration": 30,
    "interest_rate": 5,
    "implied_volatility": 25,
    "spot_range": [0.8, 1.2],
    "num_points": 30
  }'
```

---

## 🐛 Troubleshooting

### Backend Won't Start
```bash
# Kill process on port 8000
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/macOS
lsof -i :8000
kill -9 <PID>
```

### Frontend Won't Connect
1. Check backend is running: `http://localhost:8000/api/health`
2. Clear browser cache (Ctrl+Shift+Delete)
3. Check browser console (F12) for errors
4. Verify API URL in `frontend/api.js`

### Market Data Fetch Fails
1. Check internet connection
2. Verify stock symbol is correct (e.g., AAPL not Apple)
3. Try different symbol
4. Check Yahoo Finance status

---

## 📁 File Structure

```
options_greeks_calculator/
├── backend/                    # FastAPI backend
│   ├── app.py                 # Main app
│   ├── routes/api.py          # Endpoints
│   ├── models/                # Business logic
│   └── requirements.txt       # Dependencies
├── frontend/                  # Web dashboard
│   ├── index.html            # Main page
│   ├── styles.css            # Styling
│   ├── api.js                # API calls
│   └── app.js                # Logic
└── README.md                 # Documentation
```

---

## 🔑 Key Concepts

### European Options
- Can only be exercised at expiration
- Easier to price with Black-Scholes
- Used for index options

### Black-Scholes Model
- Assumes log-normal distribution of stock prices
- Assumes no dividends
- Uses d1 and d2 parameters

### At-The-Money (ATM)
- Strike = Spot price
- Usually most liquid
- Highest gamma and vega

### Implied Volatility
- Market's expectation of future volatility
- Higher IV = higher option prices
- Often different for different strikes (skew)

---

## ⚡ Performance Tips

1. **Limit surface points** to < 50 for speed
2. **Use reasonable spot ranges** (0.7-1.3 of spot)
3. **Cache market data** (not fetching every second)
4. **Clear history** if using app heavily

---

## 🛠️ Common Tasks

### Add New Parameter
1. **Backend**: Add to validation model
2. **API**: Include in calculation
3. **Frontend**: Add input field
4. **Tests**: Add test case

### Customize Colors
Edit `frontend/styles.css` - `:root` section

### Change API Host
Edit `frontend/api.js` line 2

### Use Different Volatility
1. Enter symbol and fetch (gets historical vol)
2. Manually enter IV percentage
3. Results update automatically

---

## 📚 Learning Resources

- **Black-Scholes**: https://en.wikipedia.org/wiki/Black%E2%80%93Scholes_model
- **Greeks Explained**: https://www.investopedia.com/terms/g/greek.asp
- **FastAPI**: https://fastapi.tiangolo.com/
- **Plotly.js**: https://plotly.com/javascript/
- **Options Basics**: https://www.cboe.com/

---

## 🐳 Docker Commands

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop services
docker-compose down

# Rebuild images
docker-compose build --no-cache

# Remove everything
docker-compose down -v
```

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_greeks.py::test_delta_range -v

# With coverage
pytest tests/ --cov=.

# Watch mode
pytest tests/ -v --tb=short --maxfail=1
```

---

## 📞 Getting Help

1. Check README.md
2. Check frontend/README.md
3. Check DEPLOYMENT.md
4. Check browser console (F12)
5. Check server logs
6. Create GitHub issue
7. Contact maintainers

---

## 💡 Pro Tips

1. **Stock symbols**: Use Yahoo Finance format (AAPL, SPY, etc.)
2. **Volatility**: 20-30% is typical for stocks
3. **Time decay**: Accelerates as expiration approaches
4. **Interest rates**: Usually 3-5% annual
5. **API rate limiting**: Yahoo Finance may rate limit (wait a moment)

---

**Happy calculating! 📈**
