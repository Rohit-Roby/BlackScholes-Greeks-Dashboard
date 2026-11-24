/**
 * Market Outlook page.
 * Watchlist cards -> per-symbol outlook (range, direction lean, factors, GEX ladder) -> track record.
 */

const state = {
    source: '',          // '' = server default (Databento when configured), 'synthetic' = demo
    symbols: [],
    outlooks: {},
    selected: null,
};

// ---------------------------------------------------------------- helpers

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (x, d = 1) => (x == null || !isFinite(x) ? '—' : `${(x * 100).toFixed(d)}%`);
const spct = (x, d = 1) => (x == null || !isFinite(x) ? '—' : `${x >= 0 ? '+' : '−'}${Math.abs(x * 100).toFixed(d)}%`);
const num = (x, d = 2) => (x == null || !isFinite(x) ? '—' : Number(x).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));

function cssVar(name) {
    return getComputedStyle(document.body).getPropertyValue(name).trim();
}

function leanClass(label) {
    return label === 'Lean up' ? 'up' : label === 'Lean down' ? 'down' : 'neutral';
}

function showBanner(msg, isError = false) {
    const b = $('banner');
    b.textContent = msg;
    b.classList.toggle('error', isError);
    b.classList.toggle('hidden', !msg);
}

function asofText(o) {
    const d = new Date(o.asof);
    if (isNaN(d)) return o.asof;
    return d.toLocaleString(undefined, { timeZone: 'America/New_York', weekday: 'short', day: 'numeric',
        month: 'short', hour: '2-digit', minute: '2-digit' }) + ' ET';
}

async function pool(items, limit, fn) {
    const queue = [...items];
    const workers = Array.from({ length: Math.min(limit, queue.length) }, async () => {
        while (queue.length) await fn(queue.shift());
    });
    await Promise.all(workers);
}

// ---------------------------------------------------------------- watchlist

function cardHTML(sym) {
    const o = state.outlooks[sym];
    if (o === undefined) {
        return `<div class="watch-card loading" data-sym="${esc(sym)}"><div class="top"><span class="sym">${esc(sym)}</span></div>
                <div class="row">Loading option chain…</div></div>`;
    }
    if (o.error) {
        return `<div class="watch-card failed" data-sym="${esc(sym)}" title="${esc(o.error)}"><div class="top"><span class="sym">${esc(sym)}</span></div>
                <div class="row">Unavailable</div></div>`;
    }
    const h = o.horizons[0];
    const lc = leanClass(o.direction.label);
    const active = state.selected === sym ? ' active' : '';
    return `<button class="watch-card${active}" data-sym="${esc(sym)}">
        <div class="top"><span class="sym">${esc(sym)}</span><span class="px">${num(o.spot)}</span></div>
        <div class="row"><span class="pill ${lc}">${esc(o.direction.label)} · ${pct(o.direction.p_up, 0)} up</span></div>
        <div class="row"><span>Next session</span><b>±${pct(h.expected_move_pct, 2)}</b></div>
        <div class="row"><span>Range</span><b>${num(h.low)} – ${num(h.high)}</b></div>
        <div class="row"><span>Gamma</span><span class="pill ${o.regime.gamma === 'positive' ? 'pos' : 'neg'}">${o.regime.gamma === 'positive' ? '+γ pinned' : '−γ volatile'}</span></div>
    </button>`;
}

function renderWatchlist() {
    const syms = [...state.symbols];
    if (state.selected && !syms.includes(state.selected)) syms.unshift(state.selected);
    $('watchGrid').innerHTML = syms.map(cardHTML).join('');
    $('watchGrid').querySelectorAll('button.watch-card').forEach((el) => {
        el.addEventListener('click', () => select(el.dataset.sym));
    });
}

async function loadOutlook(sym) {
    try {
        state.outlooks[sym] = await api.getOutlook(sym, state.source || undefined);
    } catch (err) {
        state.outlooks[sym] = { error: err.message || String(err) };
    }
    renderWatchlist();
    if (!state.selected && !state.outlooks[sym].error) select(sym);
    else if (state.selected === sym) renderDetail();
}

async function loadAll() {
    state.outlooks = {};
    state.selected = null;
    renderWatchlist();
    // Two at a time: a cold Databento load downloads several files per symbol.
    await pool(state.symbols, 2, loadOutlook);
    const failed = state.symbols.filter((s) => state.outlooks[s]?.error);
    if (failed.length === state.symbols.length) {
        showBanner(`Could not load any symbol: ${state.outlooks[failed[0]].error}`, true);
    } else if (failed.length) {
        showBanner(`No outlook for ${failed.join(', ')} right now (hover a card for the reason).`);
    }
    updateStatus();
}

// ---------------------------------------------------------------- detail

function select(sym) {
    state.selected = sym;
    renderWatchlist();
    renderDetail();
}

function renderDetail() {
    const o = state.outlooks[state.selected];
    if (!o || o.error) return;
    const [d1, d5] = o.horizons;
    const lc = leanClass(o.direction.label);
    $('detailTitle').textContent = `${o.symbol} ${num(o.spot)}`;
    $('detailMeta').textContent = `As of ${asofText(o)} · source: ${o.source}`;

    $('outlookCards').innerHTML = `
        <div class="o-card">
            <span class="label">Direction lean (next session)</span>
            <span class="big ${lc}">${esc(o.direction.label)}</span>
            <div class="prob-bar"><span class="mid"></span><span class="mark" style="left:${(o.direction.p_up * 100).toFixed(1)}%"></span></div>
            <div class="prob-scale"><span>Down ${pct(o.direction.p_down, 0)}</span><span>Up ${pct(o.direction.p_up, 0)}</span></div>
            <span class="small">Score ${num(o.direction.score, 2)} on a −1…+1 scale. Below ±${num(o.direction.threshold, 2)} it reads as neutral. The model never goes beyond about 62/38.</span>
        </div>
        ${rangeCard(d1, o.spot)}
        ${rangeCard(d5, o.spot)}
        <div class="o-card">
            <span class="label">Gamma regime</span>
            <span class="big ${o.regime.gamma === 'positive' ? 'up' : 'down'}">${o.regime.gamma === 'positive' ? 'Long gamma' : 'Short gamma'}</span>
            <span class="small">${esc(o.regime.text)}</span>
            <span class="small">ATM IV <b>${pct(o.vol.front_atm_iv)}</b> · RV20 <b>${pct(o.vol.rv20)}</b> · IV/RV <b>${num(o.vol.iv_rv, 2)}</b></span>
        </div>`;

    $('levelsList').innerHTML = o.levels.map((l) => `
        <li class="${l.name === 'Spot' ? 'spot' : ''}"><span>${esc(l.name)}</span>
        <span>${num(l.level)} <span class="dist">${l.name === 'Spot' ? '' : spct(l.distance_pct / 100)}</span></span></li>`).join('');

    const maxW = Math.max(...o.factors.map((f) => Math.abs(f.contribution)), 0.0001);
    $('factorList').innerHTML = o.factors.map((f) => {
        const w = Math.min(50, (Math.abs(f.contribution) / maxW) * 50);
        return `<div class="factor">
            <div class="name">${esc(f.name)}<small>weight ${Math.round(f.weight * 100)}% · score ${num(f.score, 2)}</small></div>
            <div class="contrib" title="Contribution ${num(f.contribution, 3)}"><span class="fill ${f.contribution >= 0 ? 'pos' : 'neg'}" style="width:${w}%"></span></div>
            <div class="explain">${esc(f.explanation)}</div>
        </div>`;
    }).join('') || '<p class="footnote">Not enough positioning data for a lean.</p>';

    $('disclaimer').textContent = o.disclaimer;
    drawRangeChart(o);
    renderTrack(o.calibration);
}

function rangeCard(h, spot) {
    const capped = h.capped_by && h.capped_by.length ? ` Capped by the ${h.capped_by.join(' and ')}.` : '';
    return `<div class="o-card">
        <span class="label">${esc(h.label)} range</span>
        <span class="big">${num(h.low)} – ${num(h.high)}</span>
        <span class="small">Expected move <b>±${num(h.expected_move)}</b> (${pct(h.expected_move_pct, 2)}), from ATM IV <b>${pct(h.atm_iv)}</b> (${esc(h.expiry_used)}) × <b>${num(h.range_mult, 2)}</b> for the gamma regime.${capped}</span>
        <span class="small">Chance of closing inside: <b>${pct(h.p_inside, 0)}</b></span>
    </div>`;
}

function drawRangeChart(o) {
    const g = o.gex_profile;
    const spot = o.spot;
    const [d1, d5] = o.horizons;
    const green = cssVar('--green'), red = cssVar('--red'), accent = cssVar('--accent-hover');
    const gold = cssVar('--gold'), teal = cssVar('--teal'), text = cssVar('--text-secondary'), grid = cssVar('--border');

    const lo = Math.min(d5.low, spot) - (d5.high - d5.low) * 0.35;
    const hi = Math.max(d5.high, spot) + (d5.high - d5.low) * 0.35;
    const keep = g.strikes.map((k, i) => [k, g.net_gex[i]]).filter(([k]) => k >= lo && k <= hi);

    const bars = {
        type: 'bar', orientation: 'h',
        y: keep.map(([k]) => k), x: keep.map(([, v]) => v / 1e6),
        marker: { color: keep.map(([, v]) => (v >= 0 ? green : red)), opacity: 0.75 },
        name: 'Net dealer gamma ($M per 1%)',
        hovertemplate: 'Strike %{y}<br>Net GEX %{x:.1f} $M/1%<extra></extra>',
    };

    const band = (h, color, opacity, label) => ({
        type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: h.low, y1: h.high,
        fillcolor: color, opacity, line: { width: 0 }, layer: 'below', name: label,
    });
    // Spot is labelled on the left so it never collides with a wall or the flip on the right.
    const line = (y, color, dash, label, left = false) => (y == null ? null : {
        shape: { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: y, y1: y, line: { color, width: 1.5, dash } },
        ann: { xref: 'paper', x: left ? 0.01 : 1, y, xanchor: left ? 'left' : 'right', yanchor: left ? 'top' : 'bottom',
               text: `${label} ${num(y)}`, showarrow: false, font: { size: 11, color } },
    });
    const lines = [
        line(spot, accent, 'solid', 'Spot', true),
        line(g.call_wall, green, 'dash', 'Call wall'),
        line(g.put_wall, red, 'dash', 'Put wall'),
        line(g.gamma_flip, gold, 'dot', 'Gamma flip'),
    ].filter(Boolean);

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        font: { family: 'Inter, sans-serif', size: 12, color: text },
        margin: { l: 70, r: 20, t: 40, b: 45 },
        title: { text: `Expected ranges over dealer gamma by strike`, font: { size: 13 } },
        xaxis: { title: 'Net GEX ($M per 1% move)', gridcolor: grid, zerolinecolor: grid },
        yaxis: { title: 'Price', gridcolor: grid, zerolinecolor: grid, range: [lo, hi] },
        shapes: [band(d5, teal, 0.10, '5 sessions'), band(d1, teal, 0.22, 'Next session'), ...lines.map((l) => l.shape)],
        annotations: [
            ...lines.map((l) => l.ann),
            { xref: 'paper', x: 0, y: d1.high, xanchor: 'left', yanchor: 'bottom', showarrow: false,
              text: 'Next-session range', font: { size: 10.5, color: teal } },
            { xref: 'paper', x: 0, y: d5.high, xanchor: 'left', yanchor: 'bottom', showarrow: false,
              text: '5-session range', font: { size: 10.5, color: teal } },
        ],
        showlegend: false,
        bargap: 0.15,
    };
    Plotly.react('rangeChart', [bars], layout, { displayModeBar: false, responsive: true });
}

// ---------------------------------------------------------------- track record

function renderTrack(cal) {
    if (!cal || !cal.n) {
        $('trackGrid').innerHTML = '';
        $('trackNote').textContent = 'No backtest has been run yet. Run backend/scripts/run_outlook_backtest.py to measure the model.';
        return;
    }
    const stat = (label, value, hint, cls = '') =>
        `<div class="stat ${cls}"><span class="label">${label}</span><span class="value">${value}</span><span class="hint">${hint}</span></div>`;
    const hit = cal.direction_hit_rate;
    const brierBetter = cal.brier < cal.brier_coin_flip;
    $('trackGrid').innerHTML = [
        stat('Observations', cal.n, `${cal.symbols.join(', ')} · ${cal.start} → ${cal.end}`),
        stat('Direction hit rate', hit == null ? '—' : pct(hit, 0), `on ${cal.leaned} days with a lean (coin flip = 50%)`,
             hit == null ? '' : hit > 0.5 ? 'good' : 'bad'),
        stat('Brier score', num(cal.brier, 3), `coin flip ${num(cal.brier_coin_flip, 2)}; lower is better`, brierBetter ? 'good' : 'bad'),
        stat('Range held', pct(cal.range_coverage, 0), `next close inside the range; model said ${pct(cal.range_nominal, 0)}`,
             Math.abs(cal.range_coverage - cal.range_nominal) < 0.1 ? 'good' : 'bad'),
        ...Object.entries(cal.by_regime || {}).map(([k, v]) =>
            stat(`${k === 'positive' ? 'Long' : 'Short'} gamma days`, v.n,
                 `actual move = ${num(v.median_move_ratio, 2)}× implied (median); range held ${pct(v.range_coverage, 0)}`)),
    ].join('');
    $('trackMeta').textContent = `Walk-forward: each day's closing chain vs the next close. ${cal.reliability}.`;
    $('trackNote').textContent = 'A short history like this mostly shows that the pipeline works end to end. '
        + 'Treat the hit rate as noise until there are a few hundred observations.';
}

// ---------------------------------------------------------------- status

async function updateStatus() {
    try {
        const w = await api.getOutlookWatchlist();
        const any = Object.values(state.outlooks).find((o) => o && !o.error);
        const parts = [];
        if (any) parts.push(`Data as of <b>${esc(asofText(any))}</b> (${esc(any.source)})`);
        if (w.databento_spent_today != null) {
            parts.push(`Databento spend today <b>$${num(w.databento_spent_today)}</b> of $${num(w.databento_budget)} budget`);
        }
        if (any && any.source === 'databento') parts.push('latest completed session; intraday needs Databento Live');
        $('status').innerHTML = parts.join(' · ') || '&nbsp;';
    } catch {
        $('status').textContent = '';
    }
}

// ---------------------------------------------------------------- init

async function init() {
    document.querySelectorAll('#sourceToggle .toggle-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#sourceToggle .toggle-btn').forEach((b) => b.classList.remove('active'));
            btn.classList.add('active');
            state.source = btn.dataset.value;
            showBanner('');
            loadAll();
        });
    });

    const analyze = async () => {
        const sym = $('tickerInput').value.trim().toUpperCase();
        if (!/^[A-Z0-9.\-^]{1,10}$/.test(sym)) {
            showBanner('Enter a ticker of 1-10 letters, e.g. GOOGL.', true);
            return;
        }
        showBanner('');
        state.selected = sym;
        delete state.outlooks[sym];
        state.outlooks[sym] = undefined;
        renderWatchlist();
        await loadOutlook(sym);
        if (state.outlooks[sym]?.error) showBanner(`${sym}: ${state.outlooks[sym].error}`, true);
        else select(sym);
        updateStatus();
    };
    $('analyzeButton').addEventListener('click', analyze);
    $('tickerInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') analyze(); });

    try {
        const w = await api.getOutlookWatchlist();
        state.symbols = w.symbols;
        if (w.source !== 'databento') {
            showBanner('Databento is not configured on the server (DATABENTO_API_KEY), so this page uses '
                + `the "${w.source}" source instead.`);
        }
    } catch (err) {
        showBanner(`The API is not reachable: ${err.message}`, true);
        return;
    }
    loadAll();
}

document.addEventListener('DOMContentLoaded', init);
