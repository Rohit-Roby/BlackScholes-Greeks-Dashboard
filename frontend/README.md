# Frontend

A zero-build static frontend (HTML, CSS, vanilla JavaScript and Plotly.js). No bundler, no framework.

| Page | Files | What it shows |
|---|---|---|
| Market Outlook (`index.html`) | `outlook.js`, `outlook.css` | Watchlist of direction leans and expected ranges, per-symbol detail with the factors behind the lean, a range-over-GEX chart, key levels and the backtest track record |
| Market Scanner (`scanner.html`) | `scanner.js`, `scanner.css` | Top 10 most volatile option markets, gamma exposure, SVI smile and surface, forwards and dividends, scenario explorer |

Shared: `api.js` (fetch client for the FastAPI backend) and `styles.css` (theme tokens and base components).

## Running

With Docker, Nginx serves this folder at http://localhost and proxies `/api` to the backend:

```bash
docker compose up -d --build
```

Without Docker, start the API on port 8000 and serve the folder:

```bash
python -m uvicorn backend.app:app --port 8000
cd frontend && python -m http.server 8080      # http://localhost:8080
```

`api.js` calls the backend at `http://localhost:8000/api`; the backend's `CORS_ORIGINS` must include the address the page is served from.

## Caching

Nginx caches `.css` and `.js` for 90 days, so `index.html` loads them with a version query (`outlook.js?v=2`). Bump the version when you change a file.
