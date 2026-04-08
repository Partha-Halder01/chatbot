// Dashboard auto-refresh logic
const API_BASE = '';
const REFRESH_INTERVAL = 5000;

// Clock
function updateClock() {
    const now = new Date();
    const ist = new Date(now.getTime() + (5.5 * 60 * 60 * 1000) - (now.getTimezoneOffset() * 60 * 1000));
    document.getElementById('clock').textContent = ist.toLocaleTimeString('en-IN', {
        hour12: false, timeZone: 'Asia/Kolkata'
    }) + ' IST';
}
setInterval(updateClock, 1000);
updateClock();

// Fetch helpers
async function fetchJSON(url) {
    try {
        const res = await fetch(API_BASE + url);
        if (!res.ok) throw new Error(res.statusText);
        return await res.json();
    } catch (e) {
        console.error('Fetch error:', url, e);
        return null;
    }
}

async function postJSON(url, data = {}) {
    try {
        const res = await fetch(API_BASE + url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return await res.json();
    } catch (e) {
        console.error('Post error:', url, e);
        return null;
    }
}

// Format currency
function formatINR(amount) {
    const sign = amount < 0 ? '-' : '';
    const abs = Math.abs(amount);
    return sign + '₹' + abs.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function pnlClass(amount) {
    if (amount > 0) return 'pnl-positive';
    if (amount < 0) return 'pnl-negative';
    return 'pnl-zero';
}

// Update status
async function updateStatus() {
    const data = await fetchJSON('/api/status');
    if (!data) return;

    // Mode badge
    const modeBadge = document.getElementById('mode-badge');
    modeBadge.textContent = data.mode.toUpperCase();
    modeBadge.className = 'badge ' + (data.mode === 'live' ? 'badge-live' : 'badge-paper');

    // Status badge
    const statusBadge = document.getElementById('status-badge');
    statusBadge.textContent = data.is_running ? 'RUNNING' : 'STOPPED';
    statusBadge.className = 'badge ' + (data.is_running ? 'badge-running' : 'badge-stopped');

    // Market status
    const marketBadge = document.getElementById('market-status');
    marketBadge.textContent = data.market_open ? 'Market Open' : 'Market Closed';
    marketBadge.className = 'badge ' + (data.market_open ? 'badge-market-open' : 'badge-market-closed');

    // P&L
    const pnl = data.portfolio?.daily_pnl || 0;
    const pnlEl = document.getElementById('daily-pnl');
    pnlEl.textContent = formatINR(pnl);
    pnlEl.className = 'pnl-value ' + pnlClass(pnl);

    // Win rate
    document.getElementById('win-rate').textContent = (data.portfolio?.win_rate || 0) + '%';
    document.getElementById('trade-count').textContent = (data.portfolio?.total_trades || 0) + ' trades';

    // Risk
    const risk = data.risk || {};
    const riskEl = document.getElementById('risk-status');
    riskEl.textContent = risk.is_halted ? 'HALTED' : 'OK';
    riskEl.style.color = risk.is_halted ? '#f44336' : '#4caf50';
    document.getElementById('open-positions-count').textContent =
        (risk.open_positions || 0) + '/' + (risk.max_open_positions || 2) + ' positions';
}

// Update positions table
async function updatePositions() {
    const data = await fetchJSON('/api/positions');
    const tbody = document.getElementById('positions-table');

    if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="empty-row">No open positions</td></tr>';
        return;
    }

    tbody.innerHTML = data.map(p => `
        <tr>
            <td><strong>${p.symbol}</strong></td>
            <td class="${p.side === 'BUY' ? 'signal-buy' : 'signal-sell'}">${p.side}</td>
            <td>${p.quantity}</td>
            <td>₹${p.entry_price.toFixed(2)}</td>
            <td>₹${p.current_price.toFixed(2)}</td>
            <td class="${pnlClass(p.unrealized_pnl)}">${formatINR(p.unrealized_pnl)} (${p.unrealized_pnl_pct}%)</td>
            <td>₹${p.stop_loss.toFixed(2)}</td>
            <td>₹${p.take_profit.toFixed(2)}</td>
            <td>${p.hold_duration_minutes.toFixed(0)}m</td>
        </tr>
    `).join('');
}

// Update signals table
async function updateSignals() {
    const signals = await fetchJSON('/api/signals');
    const ltp = await fetchJSON('/api/ltp');
    const tbody = document.getElementById('signals-table');

    if (!signals || signals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="empty-row">Waiting for data...</td></tr>';
        return;
    }

    tbody.innerHTML = signals.map(s => {
        const price = ltp ? (ltp[s.symbol] || 0) : 0;
        const scoreColor = s.score > 0 ? '#4caf50' : s.score < 0 ? '#f44336' : '#8899a6';
        const scoreWidth = Math.min(Math.abs(s.score), 100);
        const ind = s.indicators || {};

        return `
        <tr>
            <td><strong>${s.symbol}</strong></td>
            <td>₹${price.toFixed(2)}</td>
            <td class="signal-${s.direction.toLowerCase()}">${s.direction}</td>
            <td>
                <span class="score-bar"><span class="score-fill" style="width:${scoreWidth}%;background:${scoreColor}"></span></span>
                ${s.score.toFixed(0)}
            </td>
            <td>${ind.rsi ? ind.rsi.toFixed(1) : '-'}</td>
            <td>${ind.macd_crossover || '-'}</td>
            <td>${ind.ema_bullish !== undefined ? (ind.ema_bullish ? '↑' : '↓') : '-'}</td>
            <td>${ind.above_vwap !== undefined ? (ind.above_vwap ? '↑' : '↓') : '-'}</td>
            <td>${ind.volume_ratio ? ind.volume_ratio.toFixed(1) + 'x' : '-'}</td>
        </tr>`;
    }).join('');
}

// Update trade history
async function updateTrades() {
    const data = await fetchJSON('/api/trades');
    const container = document.getElementById('trade-history');

    if (!data || data.length === 0) {
        container.innerHTML = '<p class="empty-row">No trades yet</p>';
        return;
    }

    container.innerHTML = data.reverse().map(t => `
        <div class="trade-item">
            <span class="signal-${t.side === 'BUY' ? 'buy' : 'sell'}">${t.side}</span>
            <strong>${t.symbol}</strong>
            ${t.quantity}x @ ₹${t.entry_price.toFixed(2)} → ₹${t.exit_price.toFixed(2)}
            <span class="trade-pnl ${pnlClass(t.pnl)}">${formatINR(t.pnl)}</span>
            <span style="color:#556677;font-size:11px"> | ${t.hold_minutes}m | ${t.reason}</span>
        </div>
    `).join('');
}

// Update LLM log
async function updateLLMLog() {
    const data = await fetchJSON('/api/llm-log');
    const container = document.getElementById('llm-log');

    if (!data || data.length === 0) {
        container.innerHTML = '<p class="empty-row">No LLM analyses yet</p>';
        return;
    }

    container.innerHTML = data.reverse().map(l => `
        <div class="llm-item">
            <strong>${l.symbol}</strong>
            <span class="signal-${l.direction.toLowerCase()}">${l.direction}</span>
            Score: ${l.score} | LLM: ${l.llm_confidence}%
            ${l.llm_confirmed ? '✓ Confirmed' : '✗ Rejected'}
            <div class="llm-reasoning">${l.llm_reasoning || 'N/A'}</div>
        </div>
    `).join('');
}

// Control buttons
async function startTrading() {
    if (!confirm('Start trading?')) return;
    await postJSON('/api/control/start');
    updateStatus();
}

async function stopTrading() {
    await postJSON('/api/control/stop');
    updateStatus();
}

async function closeAll() {
    if (!confirm('CLOSE ALL POSITIONS? This cannot be undone.')) return;
    await postJSON('/api/control/close-all');
    updatePositions();
    updateStatus();
}

// Main refresh loop
function refreshAll() {
    updateStatus();
    updatePositions();
    updateSignals();
    updateTrades();
    updateLLMLog();
}

refreshAll();
setInterval(refreshAll, REFRESH_INTERVAL);
