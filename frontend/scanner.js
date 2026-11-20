/**
 * Options Market Scanner page.
 * Scanner table -> symbol analysis (GEX, smile, surface, forwards) -> scenario explorer.
 */

const state = {
    source: 'yahoo',
    symbol: null,
    analysis: null,
    strategy: 'long_straddle',
};

// ---------------------------------------------------------------- helpers

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (x, d = 1) => (x == null || !isFinite(x) ? '—' : `${(x * 100).toFixed(d)}%`);
const num = (x, d = 2) => (x == null || !isFinite(x) ? '—' : Number(x).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
const money = (x) => {
    if (x == null || !isFinite(x)) return '—';
    const r = Math.round(x);
    return `${r < 0 ? '−' : ''}$${Math.abs(r).toLocaleString()}`;
};
const compact = (x) => (x == null ? '—' : Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(x));

function cssVar(name) {
    return getComputedStyle(document.body).getPropertyValue(name).trim();
}

function baseLayout(extra = {}) {
    const text = cssVar('--text-secondary');
    const grid = cssVar('--border');
    return {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { family: 'Inter, sans-serif', size: 12, color: text },
        margin: { l: 60, r: 20, t: 40, b: 45 },
        xaxis: { gridcolor: grid, zerolinecolor: grid },
        yaxis: { gridcolor: grid, zerolinecolor: grid },
        legend: { orientation: 'h', y: 1.12, x: 0 },
        hovermode: 'x unified',
        ...extra,
    };
}
const plotConfig = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'] };

function vline(x, color, label, dash = 'dash', row = 0) {
    return {
        shape: { type: 'line', x0: x, x1: x, yref: 'paper', y0: 0, y1: 1, line: { color, width: 1.5, dash } },
        annotation: { x, yref: 'paper', y: 1.01 + 0.055 * row, text: label, showarrow: false, font: { size: 10.5, color }, xanchor: 'center', yanchor: 'bottom' },
    };
}

// Put labels of nearby lines on different rows so they don't overlap.
function stagger(lines, minGapFrac = 0.04) {
    const xs = lines.map((l) => l.shape.x0);
    const span = (Math.max(...xs) - Math.min(...xs)) || 1;
    const sorted = [...lines].sort((a, b) => a.shape.x0 - b.shape.x0);
    let prev = null, row = 0;
    sorted.forEach((l) => {
        row = prev !== null && (l.shape.x0 - prev) / span < minGapFrac * 3 ? (row + 1) % 3 : 0;
        l.annotation.y = 1.01 + 0.055 * row;
        prev = l.shape.x0;
    });
    return lines;
}

function banner(msg, type = 'warn') {
    const el = $('banner');
    if (!msg) { el.classList.add('hidden'); return; }
    el.className = `banner ${type === 'error' ? 'error' : ''}`;
    el.textContent = msg;
}

function setToggle(groupId, value) {
    document.querySelectorAll(`#${groupId} .toggle-btn`).forEach((b) => b.classList.toggle('active', b.dataset.value === value));
}

// ---------------------------------------------------------------- scanner

async function runScan() {
    const body = $('scanBody');
    body.innerHTML = '<tr class="loading-row"><td colspan="13">Scanning option chains…</td></tr>';
    banner(null);
    $('scanButton').disabled = true;
    try {
        const data = await api.getScanner({
            source: state.source,
            sortBy: $('sortBy').value,
            symbols: $('customSymbols').value.replace(/\s+/g, ''),
        });
        renderScan(data);
    } catch (err) {
        body.innerHTML = '<tr class="loading-row"><td colspan="13">Scan failed</td></tr>';
        banner(`${err.message}`, 'error');
    } finally {
        $('scanButton').disabled = false;
    }
}

function renderScan(data) {
    const rows = data.results || [];
    $('scanMeta').textContent = `${rows.length} of ${data.scanned} scanned · ranked by ${data.sort_label} · source: ${data.source === 'synthetic' ? 'demo data' : 'Yahoo Finance (delayed)'}`;
    if (data.errors?.length) {
        banner(`Skipped ${data.errors.length} symbol(s): ${data.errors.map((e) => e.symbol).join(', ')}`);
    }
    if (!rows.length) {
        $('scanBody').innerHTML = '<tr class="loading-row"><td colspan="13">No results</td></tr>';
        return;
    }
    $('scanBody').innerHTML = rows.map((r) => {
        const ivrv = r.iv_rv == null ? '—' : `<span class="${r.iv_rv > 1.2 ? 'rich' : r.iv_rv < 0.85 ? 'cheap' : ''}">${num(r.iv_rv)}</span>`;
        const regime = r.gamma_regime === 'positive' ? '<span class="pill pos">+ γ</span>' : '<span class="pill neg">− γ</span>';
        return `<tr data-symbol="${esc(r.symbol)}">
            <td>${r.rank}</td><td class="sym">${esc(r.symbol)}</td><td>${num(r.spot)}</td>
            <td>${esc(r.expiry)} <span class="dist">(${r.days}d)</span></td>
            <td><b>${pct(r.atm_iv)}</b></td><td>${pct(r.rv20)}</td><td>${ivrv}</td>
            <td>±${num(r.expected_move, 1)}%</td><td>${num(r.put_call_ratio)}</td><td>${compact(r.volume)}</td>
            <td>${regime}</td><td>${num(r.put_wall)}</td><td>${num(r.call_wall)}</td>
        </tr>`;
    }).join('');
    $('scanBody').querySelectorAll('tr').forEach((tr) => tr.addEventListener('click', () => loadSymbol(tr.dataset.symbol)));
    if (!state.symbol || !rows.some((r) => r.symbol === state.symbol)) loadSymbol(rows[0].symbol);
    else highlightRow();
}

function highlightRow() {
    $('scanBody').querySelectorAll('tr').forEach((tr) => tr.classList.toggle('selected', tr.dataset.symbol === state.symbol));
}

// ---------------------------------------------------------------- analysis

async function loadSymbol(symbol) {
    state.symbol = symbol;
    highlightRow();
    $('analysisPanel').classList.remove('hidden');
    $('symbolTitle').textContent = `${symbol} · loading…`;
    try {
        const a = await api.getAnalysis(symbol, state.source);
        state.analysis = a;
        renderAnalysis(a);
        populateScenarioControls(a);
        $('scenarioPanel').classList.remove('hidden');
        await runScenario();
    } catch (err) {
        $('symbolTitle').textContent = symbol;
        banner(err.message, 'error');
    }
}

function stat(label, value, hint = '', cls = '') {
    return `<div class="stat ${cls}"><span class="label">${esc(label)}</span><span class="value">${value}</span>${hint ? `<span class="hint">${esc(hint)}</span>` : ''}</div>`;
}

function renderAnalysis(a) {
    const g = a.gex;
    const front = a.surface.slices.find((s) => s.expiry === a.front_expiry) || a.surface.slices[0];
    $('symbolTitle').textContent = `${a.symbol}  ${num(a.spot)}`;
    $('symbolMeta').textContent = `As of ${a.asof} · ${a.source === 'synthetic' ? 'demo data' : 'Yahoo Finance, delayed'} · r = ${pct(a.rate, 2)}`;
    const ivrv = a.rv20 ? a.front_atm_iv / a.rv20 : null;
    const butterflyOk = a.surface.slices.every((s) => !s.svi || s.svi.butterfly_ok);
    $('statGrid').innerHTML = [
        stat('ATM IV', pct(a.front_atm_iv), `${front.expiry} (${front.days}d)`),
        stat('Realised vol 20d', pct(a.rv20)),
        stat('IV / RV', num(ivrv), ivrv > 1.2 ? 'options rich' : ivrv < 0.85 ? 'options cheap' : 'in line'),
        stat('Put skew', pct(front.skew_10), 'vol(−10%) − vol(+10%)'),
        stat('Gamma regime', g.regime === 'positive' ? 'Positive' : 'Negative',
            g.regime === 'positive' ? 'hedging dampens moves' : 'hedging amplifies moves', g.regime === 'positive' ? 'good' : 'bad'),
        stat('Call wall', num(g.call_wall)),
        stat('Put wall', num(g.put_wall)),
        stat('Gamma flip', num(g.gamma_flip)),
        stat('Arbitrage checks', butterflyOk && a.surface.calendar_ok ? 'Pass' : 'Flagged',
            `butterfly ${butterflyOk ? '✓' : '✗'} · calendar ${a.surface.calendar_ok ? '✓' : '✗'}`, butterflyOk && a.surface.calendar_ok ? 'good' : 'bad'),
    ].join('');
    drawGex(a);
    drawSmile(a);
    drawSurface(a);
    drawForwards(a);
}

function drawGex(a) {
    const g = a.gex;
    const green = cssVar('--green'), red = cssVar('--red'), accent = cssVar('--accent-hover'), gold = cssVar('--gold'), teal = cssVar('--teal');
    const lines = [vline(a.spot, accent, 'Spot', 'solid')];
    if (g.call_wall) lines.push(vline(g.call_wall, green, 'Call wall'));
    if (g.put_wall) lines.push(vline(g.put_wall, red, 'Put wall'));
    if (g.gamma_flip) lines.push(vline(g.gamma_flip, gold, 'Flip', 'dot'));
    stagger(lines);
    Plotly.react('gexChart', [
        { type: 'bar', x: g.strikes, y: g.call_gex.map((v) => v / 1e6), name: 'Call GEX', marker: { color: green } },
        { type: 'bar', x: g.strikes, y: g.put_gex.map((v) => v / 1e6), name: 'Put GEX', marker: { color: red } },
        { type: 'scatter', mode: 'lines', x: g.strikes, y: g.net_gex.map((v) => v / 1e6), name: 'Net', line: { color: teal, width: 2 } },
    ], baseLayout({
        title: { text: `Dealer gamma exposure by strike (expiries ≤ 45d: ${g.expiries_used.length})`, font: { size: 13 } },
        barmode: 'relative',
        margin: { l: 60, r: 20, t: 80, b: 45 },
        legend: { orientation: 'h', y: -0.18, x: 0 },
        yaxis: { title: '$M per 1% move', gridcolor: cssVar('--border') },
        xaxis: { title: 'Strike', gridcolor: cssVar('--border') },
        shapes: lines.map((l) => l.shape),
        annotations: lines.map((l) => l.annotation),
    }), plotConfig);

    const prof = g.profile;
    const profLines = [vline(a.spot, accent, 'Spot', 'solid')];
    if (g.gamma_flip) profLines.push(vline(g.gamma_flip, gold, 'Flip', 'dot'));
    Plotly.react('gexProfileChart', [{
        type: 'scatter', mode: 'lines', x: prof.spot, y: prof.gex.map((v) => v / 1e6), fill: 'tozeroy',
        line: { color: teal, width: 2 }, name: 'Total GEX',
    }], baseLayout({
        title: { text: 'Total GEX if spot moved (sticky-strike vols)', font: { size: 12 } },
        margin: { l: 60, r: 20, t: 36, b: 36 },
        showlegend: false,
        yaxis: { title: '$M / 1%', gridcolor: cssVar('--border') },
        shapes: profLines.map((l) => l.shape),
        annotations: profLines.map((l) => l.annotation),
    }), plotConfig);
    $('gexNote').textContent = g.convention + ' Open interest does not show who is long or short, so the sign convention is an assumption.';
}

function drawSmile(a) {
    const palette = [cssVar('--accent-hover'), cssVar('--teal'), cssVar('--gold'), cssVar('--purple'), cssVar('--green'), cssVar('--red')];
    const traces = [];
    a.surface.slices.forEach((s, i) => {
        const color = palette[i % palette.length];
        traces.push({ type: 'scatter', mode: 'markers', x: s.market.strike, y: s.market.iv.map((v) => v * 100),
            name: `${s.days}d market`, marker: { color, size: 6, opacity: 0.75 }, legendgroup: s.expiry, showlegend: false,
            hovertemplate: `${s.expiry}<br>K %{x}<br>IV %{y:.2f}%<extra></extra>` });
        if (s.curve) {
            traces.push({ type: 'scatter', mode: 'lines', x: s.curve.strike, y: s.curve.iv.map((v) => v * 100),
                name: `${s.days}d SVI${s.svi && !s.svi.butterfly_ok ? ' ⚠' : ''}`, line: { color, width: 2 }, legendgroup: s.expiry,
                hovertemplate: `${s.expiry} SVI<br>K %{x:.2f}<br>IV %{y:.2f}%<extra></extra>` });
        }
    });
    const lines = [vline(a.spot, cssVar('--text-secondary'), 'Spot', 'solid')];
    Plotly.react('smileChart', traces, baseLayout({
        title: { text: 'Implied volatility smile: market (dots) vs SVI fit (lines)', font: { size: 13 } },
        hovermode: 'closest',
        legend: { orientation: 'h', y: -0.15, x: 0 },
        margin: { l: 60, r: 20, t: 50, b: 80 },
        xaxis: { title: 'Strike', gridcolor: cssVar('--border') },
        yaxis: { title: 'Implied vol (%)', gridcolor: cssVar('--border') },
        shapes: lines.map((l) => l.shape), annotations: lines.map((l) => l.annotation),
    }), plotConfig);
}

function drawSurface(a) {
    const slices = a.surface.slices.filter((s) => s.curve);
    if (!slices.length) { Plotly.purge('surfaceChart3d'); return; }
    // Common moneyness grid so the surface is rectangular
    const kMin = Math.max(...slices.map((s) => Math.min(...s.curve.k)));
    const kMax = Math.min(...slices.map((s) => Math.max(...s.curve.k)));
    const n = 41;
    const ks = Array.from({ length: n }, (_, i) => kMin + (i * (kMax - kMin)) / (n - 1));
    const interp = (xs, ys, x) => {
        for (let i = 1; i < xs.length; i++) if (x <= xs[i]) {
            const t = (x - xs[i - 1]) / (xs[i] - xs[i - 1]); return ys[i - 1] + t * (ys[i] - ys[i - 1]);
        }
        return ys[ys.length - 1];
    };
    const z = slices.map((s) => ks.map((k) => interp(s.curve.k, s.curve.iv, k) * 100));
    Plotly.react('surfaceChart3d', [{
        type: 'surface', x: ks.map((k) => Math.exp(k) * 100), y: slices.map((s) => s.days), z,
        colorscale: 'Viridis', colorbar: { title: 'IV %', thickness: 12 },
        hovertemplate: 'K/F %{x:.1f}%<br>%{y} days<br>IV %{z:.2f}%<extra></extra>',
    }], {
        ...baseLayout({ margin: { l: 0, r: 0, t: 40, b: 0 } }),
        title: { text: 'SVI implied-volatility surface', font: { size: 13 } },
        scene: {
            xaxis: { title: 'Strike / forward (%)', gridcolor: cssVar('--border') },
            yaxis: { title: 'Days to expiry', gridcolor: cssVar('--border') },
            zaxis: { title: 'IV (%)', gridcolor: cssVar('--border') },
            camera: { eye: { x: 1.6, y: -1.6, z: 0.9 } },
        },
    }, plotConfig);
}

function drawForwards(a) {
    const head = `<thead><tr><th>Expiry</th><th>Days</th><th>Implied forward</th><th>Div. yield</th><th>PV dividends</th>
        <th>Implied rate</th><th>Pairs / R²</th><th>ATM vol</th><th>SVI ρ</th><th>SVI fit RMSE</th><th>Butterfly</th></tr></thead>`;
    const rows = a.surface.slices.map((s) => {
        const f = s.forward;
        const svi = s.svi;
        return `<tr><td>${esc(s.expiry)}</td><td>${s.days}</td><td>${num(s.forward_used, 2)}</td>
            <td>${pct(s.div_yield_used, 2)}</td><td>${f ? num(f.pv_dividends, 2) : '—'}</td>
            <td>${f ? pct(f.implied_rate, 2) : '—'}</td><td>${f ? `${f.n_pairs} / ${num(f.r_squared, 4)}` : 'fallback'}</td>
            <td>${pct(s.atm_vol)}</td><td>${svi ? num(svi.params.rho, 2) : '—'}</td>
            <td>${svi ? `${num(svi.rmse_vol * 100, 2)} vol pts` : '—'}</td>
            <td>${svi ? (svi.butterfly_ok ? '<span class="pill pos">pass</span>' : '<span class="pill neg">flag</span>') : '—'}</td></tr>`;
    }).join('');
    const cal = a.surface.calendar_ok
        ? '<tr><td colspan="11" style="text-align:left"><span class="pill pos">Calendar check passed</span> total variance rises with maturity at every moneyness</td></tr>'
        : `<tr><td colspan="11" style="text-align:left"><span class="pill neg">Calendar arbitrage</span> ${a.surface.calendar_violations.map((v) => `${v.T_near}y→${v.T_far}y at k=${v.k}`).join('; ')}</td></tr>`;
    $('forwardTable').innerHTML = head + `<tbody>${rows}${cal}</tbody>`;
}

// ---------------------------------------------------------------- scenarios

function populateScenarioControls(a) {
    const exp = $('expirySelect');
    const front = a.front_expiry;
    exp.innerHTML = a.expiries.map((e) => {
        const s = a.surface.slices.find((x) => x.expiry === e);
        return `<option value="${esc(e)}" ${e === front ? 'selected' : ''}>${esc(e)} (${s ? s.days : '?'}d)</option>`;
    }).join('');
    fillStrikes();
}

function fillStrikes() {
    const a = state.analysis;
    const strikes = a.strikes[$('expirySelect').value] || [];
    const atm = strikes.reduce((best, k) => (Math.abs(k - a.spot) < Math.abs(best - a.spot) ? k : best), strikes[0]);
    const near = strikes.filter((k) => Math.abs(k / a.spot - 1) <= 0.2);
    $('strikeSelect').innerHTML = near.map((k) => `<option value="${k}" ${k === atm ? 'selected' : ''}>${num(k)}${k === atm ? ' (ATM)' : ''}</option>`).join('');
}

async function runScenario() {
    if (!state.symbol) return;
    try {
        const s = await api.getScenarios(state.symbol, {
            strategy: state.strategy,
            expiry: $('expirySelect').value,
            strike: $('strikeSelect').value,
            ivShift: $('ivShift').value,
            source: state.source,
        });
        renderScenario(s);
    } catch (err) {
        banner(err.message, 'error');
    }
}

function renderScenario(s) {
    const p = s.position;
    const name = { long_call: 'Long call', long_put: 'Long put', long_straddle: 'Long straddle' }[p.strategy];
    $('positionGrid').innerHTML = [
        stat('Position', `${name} ${num(p.strike)}`, `${s.expiry} (${s.days}d)`),
        stat('Cost / contract', money(p.cost_per_contract), `${num(p.cost_per_share)} per share`),
        stat('Max loss', money(-p.max_loss), 'premium paid'),
        stat('Breakeven' + (p.breakevens.length > 1 ? 's' : ''), p.breakevens.map((b) => num(b)).join(' / ')),
        stat('Probability of profit', pct(p.probability_of_profit), p.pop_at_least_50pct ? 'meets 50% filter' : 'below 50% filter',
            p.pop_at_least_50pct ? 'good' : 'bad'),
        stat('1σ expected move', `±${num(s.expected_move.one_sigma)}`, `±${num(s.expected_move.one_sigma_pct, 1)}% · ATM IV ${pct(s.expected_move.atm_vol)}`),
    ].join('');

    $('levelsList').innerHTML = s.key_levels.map((l) => `<li class="${l.name === 'Spot' ? 'spot' : ''}">
        <span>${esc(l.name)}</span><span>${num(l.level)} <span class="dist">${l.distance_pct > 0 ? '+' : ''}${num(l.distance_pct, 1)}%</span></span></li>`).join('');

    $('scenarioCards').innerHTML = s.scenarios.map((c) => `<div class="scenario-card">
        <h4>${esc(c.title)}</h4>
        <div class="cond">${esc(c.condition)}</div>
        <div class="ctx">${esc(c.context)}</div>
        <div class="nums">
            ${c.probability != null ? `<span>Priced-in probability <b>${pct(c.probability)}</b></span>` : ''}
            <span>Position P&L <b class="${c.position_pnl >= 0 ? 'gain' : 'loss'}">${money(c.position_pnl)}</b></span>
        </div></div>`).join('');

    const grid = s.pnl_grid;
    Plotly.react('pnlChart', [{
        type: 'heatmap', z: grid.pnl, x: grid.days_elapsed.map((d) => `${d}d`), y: grid.spot_levels,
        colorscale: [[0, cssVar('--red')], [0.5, cssVar('--bg-card')], [1, cssVar('--green')]], zmid: 0,
        text: grid.pnl.map((row) => row.map((v) => money(v))), texttemplate: '%{text}', textfont: { size: 10 },
        hovertemplate: 'Spot %{y}<br>After %{x}<br>P&L %{text}<extra></extra>', colorbar: { title: '$', thickness: 10 },
    }], baseLayout({
        title: { text: `P&L per contract: spot × days elapsed${grid.iv_shift ? ` (IV ${grid.iv_shift > 0 ? '+' : ''}${grid.iv_shift * 100} pts)` : ''}`, font: { size: 13 } },
        hovermode: 'closest',
        xaxis: { title: 'Days elapsed', type: 'category' },
        yaxis: { title: 'Spot', gridcolor: cssVar('--border') },
        margin: { l: 70, r: 20, t: 40, b: 45 },
    }), plotConfig);

    const d = s.density;
    const lines = [vline(s.spot, cssVar('--accent-hover'), 'Spot', 'solid')];
    p.breakevens.forEach((b) => lines.push(vline(b, cssVar('--gold'), 'Breakeven', 'dot')));
    s.key_levels.filter((l) => /wall/.test(l.name)).forEach((l) => lines.push(vline(l.level, l.name.startsWith('Call') ? cssVar('--green') : cssVar('--red'), l.name)));
    stagger(lines, 0.12);
    // Zoom to where the distribution has mass (ignore the far tails)
    const peak = Math.max(...d.pdf);
    const mass = d.strike.filter((_, i) => d.pdf[i] > peak * 0.01);
    const xr = [Math.min(...mass, ...p.breakevens), Math.max(...mass, ...p.breakevens)];
    Plotly.react('densityChart', [{
        type: 'scatter', mode: 'lines', x: d.strike, y: d.pdf, fill: 'tozeroy', line: { color: cssVar('--teal'), width: 2 }, name: 'Density',
    }], baseLayout({
        title: { text: `Risk-neutral price distribution at ${s.expiry} (from the SVI smile)`, font: { size: 13 } },
        showlegend: false,
        xaxis: { title: 'Price at expiry', gridcolor: cssVar('--border'), range: xr },
        yaxis: { title: 'Density', gridcolor: cssVar('--border'), showticklabels: false },
        margin: { l: 50, r: 20, t: 70, b: 45 },
        shapes: lines.map((l) => l.shape), annotations: lines.map((l) => l.annotation),
    }), plotConfig);
    $('disclaimer').textContent = s.disclaimer;
}

// ---------------------------------------------------------------- wiring

function wireTabs() {
    document.querySelectorAll('#analysisTabs .tab-btn').forEach((btn) => btn.addEventListener('click', () => {
        document.querySelectorAll('#analysisTabs .tab-btn').forEach((b) => b.classList.toggle('active', b === btn));
        document.querySelectorAll('#analysisPanel .tab-pane').forEach((p) => p.classList.toggle('active', p.id === btn.dataset.tab));
        // Plotly needs a resize after a hidden container becomes visible
        document.querySelectorAll(`#${btn.dataset.tab} .chart-container`).forEach((c) => c.data && Plotly.Plots.resize(c));
    }));
}

document.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(location.search);
    if (params.get('source') === 'synthetic') { state.source = 'synthetic'; setToggle('sourceToggle', 'synthetic'); }

    document.querySelectorAll('#sourceToggle .toggle-btn').forEach((b) => b.addEventListener('click', () => {
        state.source = b.dataset.value;
        setToggle('sourceToggle', state.source);
        state.symbol = null;
        runScan();
    }));
    document.querySelectorAll('#strategyToggle .toggle-btn').forEach((b) => b.addEventListener('click', () => {
        state.strategy = b.dataset.value;
        setToggle('strategyToggle', state.strategy);
        runScenario();
    }));
    $('scanButton').addEventListener('click', runScan);
    $('sortBy').addEventListener('change', runScan);
    $('customSymbols').addEventListener('keypress', (e) => { if (e.key === 'Enter') runScan(); });
    $('expirySelect').addEventListener('change', () => { fillStrikes(); runScenario(); });
    $('strikeSelect').addEventListener('change', runScenario);
    $('ivShift').addEventListener('change', runScenario);
    $('runScenario').addEventListener('click', runScenario);
    wireTabs();
    runScan();
});
