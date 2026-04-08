// ============================================
// AI Trading Bot - Dashboard JavaScript
// ============================================

const API_BASE = '';
const REFRESH_INTERVAL = 3000;
let previousLLMCount = 0;
let previousTradeCount = 0;
let aiStreamEl = null;

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
    aiStreamEl = document.getElementById('ai-thinking-stream');
    updateClock();
    setInterval(updateClock, 1000);
    refreshAll();
    setInterval(refreshAll, REFRESH_INTERVAL);

    // Start AI thinking poll (faster)
    setInterval(pollAIThinking, 2000);
});

// ---- Clock ----
function updateClock() {
    try {
        const el = document.getElementById('clock');
        if (el) {
            el.textContent = new Date().toLocaleTimeString('en-IN', {
                hour12: false, timeZone: 'Asia/Kolkata'
            }) + ' IST';
        }
    } catch(e) {
        // Fallback
        const now = new Date();
        document.getElementById('clock').textContent = now.toLocaleTimeString() + ' IST';
    }
}

// ---- Fetch Helpers ----
async function fetchJSON(url) {
    try {
        const res = await fetch(API_BASE + url);
        if (!res.ok) throw new Error(res.statusText);
        return await res.json();
    } catch (e) {
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
        return null;
    }
}

// ---- Formatting ----
function formatINR(amount) {
    const sign = amount < 0 ? '-' : (amount > 0 ? '+' : '');
    const abs = Math.abs(amount);
    return sign + '\u20B9' + abs.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPct(pct) {
    const sign = pct > 0 ? '+' : '';
    return sign + pct.toFixed(2) + '%';
}

function pnlClass(amount) {
    if (amount > 0) return 'pnl-positive';
    if (amount < 0) return 'pnl-negative';
    return 'pnl-zero';
}

// ---- Toast Notifications ----
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
        success: '<svg width="16" height="16" fill="none"><circle cx="8" cy="8" r="6" stroke="#16a34a" stroke-width="1.5"/><path d="M5.5 8l2 2 3-4" stroke="#16a34a" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        error: '<svg width="16" height="16" fill="none"><circle cx="8" cy="8" r="6" stroke="#dc2626" stroke-width="1.5"/><path d="M6 6l4 4M10 6l-4 4" stroke="#dc2626" stroke-width="1.5" stroke-linecap="round"/></svg>',
        info: '<svg width="16" height="16" fill="none"><circle cx="8" cy="8" r="6" stroke="#6366f1" stroke-width="1.5"/><path d="M8 7v4M8 5.5v.01" stroke="#6366f1" stroke-width="1.5" stroke-linecap="round"/></svg>',
        trade: '<svg width="16" height="16" fill="none"><path d="M3 12l3-6 4 5 3-8 2 4" stroke="#f59e0b" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    };

    toast.innerHTML = (icons[type] || icons.info) + `<span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// ---- Update Status ----
async function updateStatus() {
    const data = await fetchJSON('/api/status');
    if (!data) return;

    // Mode badge
    const modeBadge = document.getElementById('mode-badge');
    const isLive = data.mode === 'live';
    modeBadge.innerHTML = `<span class="badge-dot"></span>${data.mode.toUpperCase()}`;
    modeBadge.className = 'badge ' + (isLive ? 'badge-live' : 'badge-paper');

    // Mode toggle
    document.getElementById('mode-switch').checked = isLive;
    document.getElementById('mode-label').textContent = isLive ? 'LIVE Mode' : 'Paper Mode';

    // Status badge
    const statusBadge = document.getElementById('status-badge');
    statusBadge.innerHTML = `<span class="badge-dot"></span>${data.is_running ? 'RUNNING' : 'STOPPED'}`;
    statusBadge.className = 'badge ' + (data.is_running ? 'badge-running' : 'badge-stopped');

    // Market status
    const marketBadge = document.getElementById('market-status');
    marketBadge.textContent = data.market_open ? 'Market Open' : 'Market Closed';
    marketBadge.className = 'badge ' + (data.market_open ? 'badge-market-open' : 'badge-market-closed');

    // Uptime
    const upMin = Math.floor(data.uptime_minutes || 0);
    document.getElementById('uptime').textContent = upMin >= 60 ? `${Math.floor(upMin/60)}h ${upMin%60}m` : `${upMin}m`;

    // P&L
    const portfolio = data.portfolio || {};
    const pnl = portfolio.daily_pnl || 0;
    const pnlEl = document.getElementById('daily-pnl');
    pnlEl.textContent = formatINR(pnl);
    pnlEl.className = 'stat-number ' + pnlClass(pnl);

    const pnlCard = document.getElementById('pnl-card');
    pnlCard.className = 'stat-card stat-pnl ' + (pnl > 0 ? 'pnl-positive' : pnl < 0 ? 'pnl-negative' : '');

    const capital = data.risk?.capital || 100000;
    const pnlPct = capital > 0 ? (pnl / capital) * 100 : 0;
    const pnlPctEl = document.getElementById('daily-pnl-pct');
    pnlPctEl.textContent = formatPct(pnlPct);
    pnlPctEl.className = 'stat-change ' + pnlClass(pnl);

    // Trades
    document.getElementById('total-trades').textContent = portfolio.total_trades || 0;
    document.getElementById('win-count').textContent = (portfolio.winning_trades || 0) + 'W';
    document.getElementById('loss-count').textContent = (portfolio.losing_trades || 0) + 'L';
    const winBarPct = portfolio.total_trades > 0 ? (portfolio.winning_trades / portfolio.total_trades) * 100 : 0;
    document.getElementById('win-bar').style.width = winBarPct + '%';
    document.getElementById('trades-badge').textContent = portfolio.total_trades || 0;

    // Win rate
    document.getElementById('win-rate').textContent = (portfolio.win_rate || 0) + '%';
    document.getElementById('avg-win').textContent = formatINR(portfolio.avg_win || 0);
    document.getElementById('avg-loss').textContent = formatINR(portfolio.avg_loss || 0);

    // Risk
    const risk = data.risk || {};
    const riskEl = document.getElementById('risk-status');
    riskEl.textContent = risk.is_halted ? 'HALTED' : 'OK';
    riskEl.className = 'stat-number ' + (risk.is_halted ? 'risk-halted' : 'risk-ok');
    document.getElementById('open-pos-count').textContent = `${risk.open_positions || 0}/${risk.max_open_positions || 2}`;
    document.getElementById('loss-limit').textContent = '\u20B9' + (risk.daily_loss_limit || 0).toLocaleString('en-IN');

    // Capital
    document.getElementById('capital').textContent = '\u20B9' + (risk.capital || 0).toLocaleString('en-IN');
}

// ---- Update Positions ----
async function updatePositions() {
    const data = await fetchJSON('/api/positions');
    const tbody = document.getElementById('positions-table');
    const badge = document.getElementById('positions-badge');

    badge.textContent = (data && data.length) || 0;

    if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="empty-row"><div class="empty-state"><svg width="40" height="40" viewBox="0 0 40 40" fill="none"><circle cx="20" cy="20" r="16" stroke="#e2e8f0" stroke-width="2" stroke-dasharray="4 4"/><path d="M15 20h10" stroke="#cbd5e1" stroke-width="2" stroke-linecap="round"/></svg><span>No open positions</span></div></td></tr>';
        return;
    }

    tbody.innerHTML = data.map(p => {
        const pclass = pnlClass(p.unrealized_pnl);
        return `
        <tr>
            <td><strong>${p.symbol}</strong></td>
            <td><span class="signal-${p.side.toLowerCase()}">${p.side}</span></td>
            <td>${p.quantity}</td>
            <td>\u20B9${p.entry_price.toFixed(2)}</td>
            <td>\u20B9${p.current_price.toFixed(2)}</td>
            <td class="${pclass}"><strong>${formatINR(p.unrealized_pnl)}</strong><br><small>${formatPct(p.unrealized_pnl_pct)}</small></td>
            <td>\u20B9${p.stop_loss.toFixed(2)}</td>
            <td>\u20B9${p.take_profit.toFixed(2)}</td>
            <td>${p.hold_duration_minutes.toFixed(0)}m</td>
        </tr>`;
    }).join('');
}

// ---- Update Signals ----
async function updateSignals() {
    const signals = await fetchJSON('/api/signals');
    const ltp = await fetchJSON('/api/ltp');
    const tbody = document.getElementById('signals-table');

    if (!signals || signals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="empty-row"><div class="empty-state"><div class="pulse-ring"></div><span>Waiting for market data...</span></div></td></tr>';
        return;
    }

    tbody.innerHTML = signals.map(s => {
        const price = ltp ? (ltp[s.symbol] || 0) : 0;
        const scoreColor = s.score > 0 ? '#16a34a' : s.score < 0 ? '#dc2626' : '#94a3b8';
        const scoreWidth = Math.min(Math.abs(s.score), 100);
        const ind = s.indicators || {};
        const dir = s.direction.toLowerCase();

        function indCell(val, upCondition) {
            if (val === undefined || val === null) return '<span class="ind-neutral">-</span>';
            return upCondition ? '<span class="ind-up">&#9650;</span>' : '<span class="ind-down">&#9660;</span>';
        }

        const rsiVal = ind.rsi !== undefined ? ind.rsi.toFixed(1) : '-';
        const rsiClass = ind.rsi > 70 ? 'ind-down' : ind.rsi < 30 ? 'ind-up' : 'ind-neutral';

        return `
        <tr>
            <td><strong>${s.symbol}</strong></td>
            <td>\u20B9${price.toFixed(2)}</td>
            <td><span class="signal-${dir}">${s.direction}</span></td>
            <td><div class="score-cell"><span class="score-bar"><span class="score-fill" style="width:${scoreWidth}%;background:${scoreColor}"></span></span><span class="score-val" style="color:${scoreColor}">${s.score.toFixed(0)}</span></div></td>
            <td><span class="${rsiClass}">${rsiVal}</span></td>
            <td>${ind.macd_crossover === 'bullish' ? '<span class="ind-up">Bull</span>' : ind.macd_crossover === 'bearish' ? '<span class="ind-down">Bear</span>' : '<span class="ind-neutral">-</span>'}</td>
            <td>${indCell(ind.ema_bullish, ind.ema_bullish)}</td>
            <td>${indCell(ind.above_vwap, ind.above_vwap)}</td>
            <td>${ind.volume_ratio ? (ind.volume_spike ? '<span class="ind-up">' + ind.volume_ratio.toFixed(1) + 'x</span>' : '<span class="ind-neutral">' + ind.volume_ratio.toFixed(1) + 'x</span>') : '-'}</td>
            <td>${ind.bb_position !== undefined ? '<span class="ind-neutral">' + (ind.bb_position * 100).toFixed(0) + '%</span>' : '-'}</td>
        </tr>`;
    }).join('');
}

// ---- Update Trade History ----
async function updateTrades() {
    const data = await fetchJSON('/api/trades');
    const container = document.getElementById('trade-history');

    if (!data || data.length === 0) {
        container.innerHTML = '<div class="empty-state" style="padding:40px"><span>No trades executed yet</span></div>';
        return;
    }

    // Notify on new trade
    if (data.length > previousTradeCount && previousTradeCount > 0) {
        const latest = data[data.length - 1];
        const pnlStr = formatINR(latest.pnl);
        showToast(`Trade closed: ${latest.symbol} ${pnlStr}`, latest.pnl >= 0 ? 'success' : 'error');
    }
    previousTradeCount = data.length;

    container.innerHTML = [...data].reverse().map(t => {
        const pclass = pnlClass(t.pnl);
        const sideClass = t.side === 'BUY' ? 'trade-side-buy' : 'trade-side-sell';
        return `
        <div class="trade-item">
            <span class="trade-side ${sideClass}">${t.side}</span>
            <div class="trade-info">
                <div class="trade-symbol">${t.symbol}</div>
                <div class="trade-details">${t.quantity}x @ \u20B9${t.entry_price.toFixed(2)} \u2192 \u20B9${t.exit_price.toFixed(2)} | ${t.hold_minutes}m | ${t.reason}</div>
            </div>
            <div class="trade-pnl ${pclass}">
                ${formatINR(t.pnl)}
                <div class="trade-pnl-sub">${formatPct(t.pnl_pct)}</div>
            </div>
        </div>`;
    }).join('');
}

// ---- AI Thinking Live Stream ----
async function pollAIThinking() {
    const data = await fetchJSON('/api/ai-thinking');
    if (!data) return;

    const statusText = document.getElementById('ai-status-text');
    const pulse = document.getElementById('ai-pulse');
    const loader = document.getElementById('ai-loader');

    // Update AI summary stats
    document.getElementById('ai-count').textContent = data.total_analyses || 0;
    document.getElementById('ai-confirmed').textContent = data.confirmed || 0;
    document.getElementById('ai-rejected').textContent = data.rejected || 0;
    document.getElementById('ai-avg-conf').textContent = (data.avg_confidence || 0).toFixed(0) + '%';

    // Check if AI is currently thinking
    if (data.is_thinking) {
        statusText.textContent = 'Analyzing ' + (data.current_symbol || '...');
        statusText.className = 'ai-status-text active';
        pulse.className = 'ai-pulse active';
        loader.className = 'ai-loader';
    } else {
        statusText.textContent = data.total_analyses > 0 ? 'Monitoring' : 'Idle';
        statusText.className = 'ai-status-text';
        pulse.className = 'ai-pulse';
        loader.className = 'ai-loader hidden';
    }

    // Render entries
    const entries = data.entries || [];
    if (entries.length === 0) return;

    // Only update if new entries
    if (entries.length <= previousLLMCount && !data.is_thinking) return;
    previousLLMCount = entries.length;

    // Clear welcome message
    const welcome = aiStreamEl.querySelector('.ai-welcome');
    if (welcome) welcome.remove();

    // Render new entries (most recent on top)
    aiStreamEl.innerHTML = [...entries].reverse().map(e => {
        const isConfirmed = e.llm_confirmed;
        const entryClass = isConfirmed ? 'confirmed' : (e.llm_confidence > 0 ? 'rejected' : '');
        const resultBadge = e.llm_confidence > 0
            ? (isConfirmed
                ? '<span class="ai-result-badge ai-result-confirmed">Confirmed</span>'
                : '<span class="ai-result-badge ai-result-rejected">Rejected</span>')
            : '<span class="ai-result-badge" style="background:#f1f5f9;color:#94a3b8">Pending</span>';

        const confColor = e.llm_confidence >= 70 ? '#16a34a' : e.llm_confidence >= 40 ? '#f59e0b' : '#dc2626';

        const signalClass = e.direction === 'BUY' ? 'signal-buy' : e.direction === 'SELL' ? 'signal-sell' : 'signal-hold';

        // Build thinking text with indicators
        let thinkingText = '';
        if (e.indicators) {
            const ind = e.indicators;
            thinkingText += `<strong>Analyzing ${e.symbol}...</strong><br>`;
            if (ind.rsi !== undefined) thinkingText += `RSI(14): ${ind.rsi.toFixed(1)} ${ind.rsi_trend === 'rising' ? '&#9650;' : '&#9660;'} | `;
            if (ind.macd_crossover) thinkingText += `MACD: ${ind.macd_crossover} | `;
            if (ind.ema_bullish !== undefined) thinkingText += `EMA: ${ind.ema_bullish ? 'Bullish' : 'Bearish'} | `;
            if (ind.above_vwap !== undefined) thinkingText += `VWAP: ${ind.above_vwap ? 'Above' : 'Below'} | `;
            if (ind.volume_ratio) thinkingText += `Vol: ${ind.volume_ratio.toFixed(1)}x`;
            thinkingText += `<br><br>`;
        }
        thinkingText += `Signal Score: <strong style="color:${e.score > 0 ? '#16a34a' : '#dc2626'}">${e.score > 0 ? '+' : ''}${e.score.toFixed(1)}</strong><br>`;
        if (e.llm_reasoning) {
            thinkingText += `<br>AI says: <em>"${e.llm_reasoning}"</em>`;
        }

        return `
        <div class="ai-entry ${entryClass}">
            <div class="ai-entry-header">
                <span class="ai-entry-symbol">${e.symbol}</span>
                <span class="ai-entry-time">${e.timestamp ? new Date(e.timestamp).toLocaleTimeString('en-IN', {hour12: false, timeZone: 'Asia/Kolkata'}) : ''}</span>
            </div>
            <div class="ai-entry-signal">
                <span class="${signalClass}">${e.direction}</span>
                <span style="color:var(--text-muted)">Score: ${e.score.toFixed(0)}</span>
            </div>
            <div class="ai-entry-thinking">${thinkingText}</div>
            <div class="ai-entry-result">
                ${resultBadge}
                <div class="ai-confidence-bar"><div class="ai-confidence-fill" style="width:${e.llm_confidence}%;background:${confColor}"></div></div>
                <span class="ai-confidence-val">${e.llm_confidence}%</span>
            </div>
        </div>`;
    }).join('');
}

// ---- Control Buttons ----
async function startTrading() {
    if (!confirm('Start trading?')) return;
    const result = await postJSON('/api/control/start');
    if (result) showToast('Trading started', 'success');
    updateStatus();
}

async function stopTrading() {
    const result = await postJSON('/api/control/stop');
    if (result) showToast('Trading paused', 'info');
    updateStatus();
}

async function closeAll() {
    if (!confirm('CLOSE ALL POSITIONS?\nThis will market-sell all open positions immediately.')) return;
    const result = await postJSON('/api/control/close-all');
    if (result) showToast('All positions closed', 'error');
    updatePositions();
    updateStatus();
}

async function toggleMode() {
    const isLive = document.getElementById('mode-switch').checked;
    const mode = isLive ? 'live' : 'paper';

    if (isLive && !confirm('Switch to LIVE trading?\nReal money will be used for trades.')) {
        document.getElementById('mode-switch').checked = false;
        return;
    }

    const result = await postJSON('/api/control/mode', { mode });
    if (result) {
        showToast(`Switched to ${mode.toUpperCase()} mode`, isLive ? 'error' : 'info');
    }
    updateStatus();
}

// ---- Main Refresh Loop ----
function refreshAll() {
    updateStatus();
    updatePositions();
    updateSignals();
    updateTrades();
}

