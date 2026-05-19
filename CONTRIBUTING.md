# Contributing Guide

Thank you for your interest in contributing to the Options Greeks Calculator! This guide will help you get started.

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the code, not the person
- Help others learn and grow

## Getting Started

### 1. Fork & Clone
```bash
git clone https://github.com/yourusername/options_greeks_calculator.git
cd options_greeks_calculator
```

### 2. Create Feature Branch
```bash
git checkout -b feature/your-feature-name
```

### 3. Setup Development Environment
```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install pytest pytest-cov black flake8

# Frontend
cd ../frontend
# No setup needed - use any HTTP server
```

### 4. Make Changes
Follow the guidelines below when making changes.

### 5. Test Your Changes
```bash
# Backend unit tests
cd backend
pytest tests/ -v
pytest tests/ --cov=. --cov-report=html

# Frontend - test in browser
```

### 6. Commit & Push
```bash
git add .
git commit -m "feat: Add your feature description"
git push origin feature/your-feature-name
```

### 7. Create Pull Request
- Describe what you changed and why
- Reference related issues
- Include test results
- Request review from maintainers

---

## Development Guidelines

### Code Style

#### Python (Backend)
- Follow PEP 8
- Use Black for formatting
- Line length: 100 characters
- Use type hints

```python
# Good
def calculate_option_price(
    spot: float,
    strike: float,
    time: float
) -> float:
    """Calculate option price using Black-Scholes."""
    return spot * 0.5  # Simplified

# Format with Black
black backend/
```

#### JavaScript (Frontend)
- Use ESLint
- Use Prettier for formatting
- Semicolons required
- Use const/let (no var)

```javascript
// Good
const calculateGreeks = async (params) => {
    const result = await api.calculateGreeks(params);
    return result;
};
```

### Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Python Classes | PascalCase | `BlackScholesCalculator` |
| Python Functions | snake_case | `calculate_greeks()` |
| Python Constants | UPPER_SNAKE_CASE | `MAX_ITERATIONS = 100` |
| JavaScript Classes | PascalCase | `GreeksAPI` |
| JavaScript Functions | camelCase | `fetchMarketData()` |
| JavaScript Constants | UPPER_SNAKE_CASE | `API_TIMEOUT = 5000` |
| CSS Classes | kebab-case | `greeks-card` |
| CSS IDs | camelCase | `calculateButton` |

### Comments & Documentation

**Python:**
```python
def calculate_delta(spot: float, strike: float, time: float) -> float:
    """
    Calculate Delta for a call option.
    
    Args:
        spot: Current spot price
        strike: Strike price
        time: Time to expiration (years)
    
    Returns:
        Delta value (0 to 1)
    """
    # Implementation
```

**JavaScript:**
```javascript
/**
 * Calculate all Greeks
 * @param {Object} params - Parameters
 * @param {number} params.spotPrice - Spot price
 * @returns {Promise<Object>} Greeks result
 */
async function calculateGreeks(params) {
    // Implementation
}
```

### Testing

#### Backend Tests
```python
# test_greeks.py
import pytest
from models.greeks_calculator import BlackScholesCalculator

def test_delta_range():
    """Test delta is within valid range."""
    delta = BlackScholesCalculator.calculate_delta(100, 100, 0.25, 0.05, 0.2)
    assert 0 <= delta <= 1

def test_greeks_calculation():
    """Test complete Greeks calculation."""
    result = BlackScholesCalculator.calculate_all_greeks(
        S=100, K=100, T_days=30, r=0.05, sigma=0.2
    )
    assert result.call_price > 0
    assert result.put_price > 0
```

#### Frontend Tests
- Test in multiple browsers
- Test with various screen sizes
- Test API error handling
- Test with mock data

### Performance Considerations

**Backend:**
- Cache market data (5-minute TTL)
- Optimize numpy operations
- Use connection pooling for databases
- Monitor API response times

**Frontend:**
- Lazy load charts
- Debounce slider inputs
- Minimize API calls
- Use local storage for history

---

## Feature Development

### Adding a New Greek or Calculation

1. **Backend Changes**
```python
# models/greeks_calculator.py
@staticmethod
def calculate_my_greek(S, K, T, r, sigma):
    """Docstring explaining the calculation."""
    # Implementation
    return value

# Add to calculate_all_greeks()
my_greek = BlackScholesCalculator.calculate_my_greek(...)

# Update GreeksResult dataclass
@dataclass
class GreeksResult:
    # ... existing fields ...
    my_greek: float

# Update validation model
class GreeksResponse(BaseModel):
    # ... existing fields ...
    my_greek: float
```

2. **API Endpoint** (if needed)
```python
# routes/api.py
@router.post("/my-greek")
async def calculate_my_greek(request: MyGreekRequest):
    """Calculate my custom greek."""
    result = BlackScholesCalculator.calculate_my_greek(...)
    return {"my_greek": result}
```

3. **Frontend Changes**
```javascript
// app.js - displayGreeksCards()
const cards = [
    // ... existing cards ...
    { title: 'My Greek', value: greeks.my_greek, label: 'units' }
];

// Update API call
async calculateGreeks() {
    const result = await api.calculateGreeks(params);
    // Now contains my_greek
}
```

4. **Tests**
```python
def test_my_greek():
    """Test my greek calculation."""
    result = BlackScholesCalculator.calculate_my_greek(...)
    assert isinstance(result, float)
    # Add assertions based on expected behavior
```

### Adding a New Visualization

1. **Backend** - Add data endpoint if needed
2. **Frontend** - Add tab and visualization
```html
<!-- index.html -->
<button class="tab-button" data-tab="my-viz">My Viz</button>

<div id="my-viz" class="tab-pane">
    <div id="myVizChart" class="chart-container" style="height: 500px;"></div>
</div>
```

```javascript
// app.js
switchTab(tabName) {
    if (tabName === 'my-viz') {
        this.visualizeMyData();
    }
}

visualizeMyData() {
    // Create visualization with Plotly
    const trace = { /* ... */ };
    Plotly.newPlot('myVizChart', [trace], layout);
}
```

---

## Bug Reports

When reporting bugs, include:
- Description of the issue
- Steps to reproduce
- Expected behavior
- Actual behavior
- Screenshots/logs if applicable
- Browser/OS information
- Python version (for backend)

**Example:**
```
Title: Greeks calculation incorrect for deep ITM options

Description: When calculating Greeks for deep ITM options, 
the delta value exceeds 1.

Steps:
1. Enter spot = 200, strike = 100
2. Click Calculate
3. Observe delta_call > 1

Expected: delta_call should be <= 1
Actual: delta_call = 1.2345

Environment: Chrome 120, Windows 11, Python 3.11
```

---

## Feature Requests

When suggesting features:
- Explain the use case
- Describe expected behavior
- Provide examples if applicable
- Consider performance implications

**Example:**
```
Title: Add implied volatility surface visualization

Description: Currently can't visualize how implied volatility 
changes across strikes and expirations.

Use Case: Traders want to see IV skew and term structure

Expected: 3D surface plot or heatmap of IV across strikes/expirations

Effort: Medium - needs backend data aggregation
```

---

## Pull Request Process

### Before Submitting
1. ✓ Tests pass: `pytest tests/ -v`
2. ✓ Code formatted: `black backend/`
3. ✓ Linting: `flake8 backend/`
4. ✓ Documentation updated
5. ✓ Changelog updated if applicable
6. ✓ No breaking changes (or documented)

### PR Description Template
```markdown
## Description
Brief explanation of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Enhancement
- [ ] Documentation
- [ ] Refactoring

## Related Issues
Closes #123

## Testing
- [ ] Added unit tests
- [ ] Tested in browser (Firefox, Chrome)
- [ ] Tested on mobile
- [ ] API tested with Postman/curl

## Checklist
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] No console errors/warnings
- [ ] Backward compatible
```

---

## Release Process

1. Update version in `app.py`
2. Update CHANGELOG
3. Create release branch
4. Run full test suite
5. Merge to main
6. Tag release: `git tag v1.0.0`
7. Push tag: `git push origin v1.0.0`
8. Create GitHub release

---

## Questions?

- Check README.md and documentation
- Browse existing issues
- Check discussions
- Ask in pull request comments
- Contact maintainers

---

## Contributors

We appreciate all contributions! See [CONTRIBUTORS.md](CONTRIBUTORS.md) for a list of amazing people who have helped.

---

Thank you for contributing! 🎉
