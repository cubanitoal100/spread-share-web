const TICKERS = [
    'SPX','SPY','QQQ','IWM','DIA','VIX',
    'AAPL','MSFT','NVDA','META','GOOGL','GOOG','AMZN','TSLA','NFLX',
    'AMD','INTC','QCOM','AVGO','MU','AMAT',
    'JPM','GS','BAC','MS','C','WFC','V','MA','PYPL','SQ',
    'XOM','CVX','COP','SLB',
    'BA','GE','CAT','HON',
    'WMT','COST','TGT','AMZN',
    'DIS','NFLX','CMCSA',
    'COIN','MSTR','HOOD','RIVN','PLTR','SOFI',
    'GME','AMC','BB',
    'GLD','SLV','TLT','HYG','EEM',
    'UBER','LYFT','SNAP','RBLX',
];

const STRATEGIES = {
    PCS: {
        label: 'Put Credit Spread',
        strikes: [
            { id: 'k_short', label: 'Sell Strike (Short Put)' },
            { id: 'k_long',  label: 'Buy Strike (Long Put, lower)' },
        ]
    },
    CCS: {
        label: 'Call Credit Spread',
        strikes: [
            { id: 'k_short', label: 'Sell Strike (Short Call)' },
            { id: 'k_long',  label: 'Buy Strike (Long Call, higher)' },
        ]
    },
    IC: {
        label: 'Iron Condor',
        strikes: [
            { id: 'put_buy',   label: 'Buy Put (Lowest)' },
            { id: 'put_sell',  label: 'Sell Put' },
            { id: 'call_sell', label: 'Sell Call' },
            { id: 'call_buy',  label: 'Buy Call (Highest)' },
        ]
    },
    IB: {
        label: 'Iron Butterfly',
        strikes: [
            { id: 'put_buy',  label: 'Buy Put (Wing)' },
            { id: 'body',     label: 'Sell Body (ATM – both Put & Call)' },
            { id: 'call_buy', label: 'Buy Call (Wing)' },
        ]
    },
    CSP: {
        label: 'Cash Secured Put',
        strikes: [
            { id: 'k_short', label: 'Sell Strike (Short Put)' },
        ]
    },
    CC: {
        label: 'Covered Call',
        strikes: [
            { id: 'k_short', label: 'Sell Strike (Short Call)' },
        ]
    },
    JL: {
        label: 'Jade Lizard',
        strikes: [
            { id: 'put_sell',  label: 'Sell Put' },
            { id: 'call_sell', label: 'Sell Call' },
            { id: 'call_buy',  label: 'Buy Call' },
        ]
    },
};

document.addEventListener('DOMContentLoaded', () => {
    const elExp       = document.getElementById('expiration_menu');
    const elCredit    = document.getElementById('net_credit');
    const elPrice     = document.getElementById('current_price');
    const elComment   = document.getElementById('txt_comment');
    const elStrategy  = document.getElementById('strategy_select');
    const elTickerIn  = document.getElementById('ticker_input');
    const elDrop      = document.getElementById('ticker_dropdown');
    const elStrikes   = document.getElementById('strikes_container');
    const btnShare    = document.getElementById('btn_share');
    const btnRefresh  = document.getElementById('btn_refresh_price');
    const statusMsg   = document.getElementById('status_msg');
    const chartImg    = document.getElementById('chart_img');
    const chartPH     = document.getElementById('chart_placeholder');

    let debounceTimer = null;
    let currentChartBlob = null;
    let baseChartImg = null;
    let chartAbortController = null;
    let selectedTicker = 'SPX';

    // ── Ticker combobox ──────────────────────────────────────────────────────

    function buildDropdown(filter) {
        const q = filter.toUpperCase().trim();
        const matches = q
            ? TICKERS.filter(t => t.includes(q))
            : TICKERS.slice(0, 20);

        elDrop.innerHTML = '';
        if (matches.length === 0 && q) {
            const d = document.createElement('div');
            d.className = 'ticker-option';
            d.textContent = q + '  (use as-is)';
            d.addEventListener('mousedown', () => selectTicker(q));
            elDrop.appendChild(d);
        } else {
            matches.forEach(t => {
                const d = document.createElement('div');
                d.className = 'ticker-option' + (t === selectedTicker ? ' selected' : '');
                d.textContent = t;
                d.addEventListener('mousedown', () => selectTicker(t));
                elDrop.appendChild(d);
            });
        }
        elDrop.style.display = matches.length > 0 || q ? 'block' : 'none';
    }

    function resetForm() {
        renderStrikes(elStrategy.value);
        elCredit.value  = '';
        elComment.value = '';
        baseChartImg = null;
        currentChartBlob = null;
        chartImg.style.display = 'none';
        chartPH.style.display  = 'block';
    }

    function selectTicker(ticker) {
        selectedTicker = ticker.toUpperCase().trim();
        elTickerIn.value = selectedTicker;
        elDrop.style.display = 'none';
        resetForm();
        loadMarketData();
    }

    elTickerIn.addEventListener('focus', () => buildDropdown(elTickerIn.value));
    elTickerIn.addEventListener('input', () => buildDropdown(elTickerIn.value));
    elTickerIn.addEventListener('blur', () => {
        setTimeout(() => { elDrop.style.display = 'none'; }, 150);
    });
    elTickerIn.addEventListener('keydown', e => {
        if (e.key === 'Enter') {
            const val = elTickerIn.value.trim().toUpperCase();
            if (val) selectTicker(val);
            e.preventDefault();
        }
    });

    // Init ticker
    elTickerIn.value = 'SPX';

    // ── Strike inputs ─────────────────────────────────────────────────────────

    function renderStrikes(strategy) {
        elStrikes.innerHTML = '';
        const cfg = STRATEGIES[strategy];
        if (!cfg) return;
        cfg.strikes.forEach(s => {
            const grp = document.createElement('div');
            grp.className = 'input-group';
            grp.innerHTML = `
                <label>${s.label}:</label>
                <input type="number" id="strike_${s.id}" placeholder="e.g. ${exampleStrike()}" step="0.5">
            `;
            elStrikes.appendChild(grp);
            grp.querySelector('input').addEventListener('keyup', onStrikeChange);
        });
    }

    function exampleStrike() {
        const p = parseFloat(elPrice.value);
        return p ? Math.round(p / 5) * 5 : '5500';
    }

    function collectStrikes() {
        const strategy = elStrategy.value;
        const cfg = STRATEGIES[strategy];
        if (!cfg) return {};
        const out = {};
        cfg.strikes.forEach(s => {
            const el = document.getElementById(`strike_${s.id}`);
            out[s.id] = el ? el.value : '';
        });
        return out;
    }

    function strikesReady() {
        const vals = Object.values(collectStrikes());
        return vals.length > 0 && vals.every(v => v !== '');
    }

    // ── Status ────────────────────────────────────────────────────────────────

    function setStatus(msg, color = 'var(--text-muted)') {
        statusMsg.textContent = msg;
        statusMsg.style.color = color;
    }

    // ── Market data ───────────────────────────────────────────────────────────

    async function loadMarketData() {
        setStatus(`Connecting to ${selectedTicker}...`, 'var(--primary)');
        try {
            const res = await fetch(`/api/market_data?symbol=${encodeURIComponent(selectedTicker)}`);
            const data = await res.json();
            if (data.error) throw new Error(data.error);

            elPrice.value = data.current_price.toFixed(2);

            elExp.innerHTML = '';
            const exps = data.expirations;
            if (exps.length > 0) {
                exps.forEach(d => {
                    const o = document.createElement('option');
                    o.value = d;
                    o.textContent = d;
                    elExp.appendChild(o);
                });
            } else {
                elExp.innerHTML = '<option>No data</option>';
            }
            setStatus(`${selectedTicker} connected. Price: $${data.current_price.toFixed(2)}`, 'var(--success)');
        } catch (e) {
            setStatus('Connection error: ' + e.message, 'red');
        }
    }

    // ── Auto-calculate credit ─────────────────────────────────────────────────

    async function autoCalcCredit() {
        const strategy = elStrategy.value;
        const exp_date = elExp.value;
        if (!strikesReady() || !exp_date || exp_date === 'Loading...' || exp_date === 'No data') return;

        setStatus('Calculating premium...', 'yellow');
        try {
            const res = await fetch('/api/calculate_credit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    strategy,
                    symbol: selectedTicker,
                    exp_date,
                    strikes: collectStrikes(),
                }),
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);

            elCredit.value = data.net_credit.toFixed(2);
            setStatus('Credit auto-calculated.', 'var(--success)');
            await generateBaseChart();
        } catch (e) {
            setStatus('Error: ' + e.message, 'red');
            elCredit.value = '';
        }
    }

    function onStrikeChange() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(autoCalcCredit, 300);
    }

    // ── Chart generation ──────────────────────────────────────────────────────

    async function generateBaseChart() {
        const net_credit = elCredit.value;
        if (!net_credit || !strikesReady()) return;

        if (chartAbortController) chartAbortController.abort();
        chartAbortController = new AbortController();

        setStatus('Generating chart...', 'var(--primary)');
        try {
            const res = await fetch('/api/generate_chart', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    strategy:      elStrategy.value,
                    symbol:        selectedTicker,
                    strikes:       collectStrikes(),
                    net_credit,
                    current_price: elPrice.value,
                }),
                signal: chartAbortController.signal,
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || 'Error generating chart');
            }

            const blob = await res.blob();
            const url  = URL.createObjectURL(blob);
            baseChartImg = new Image();
            baseChartImg.onload = () => renderWithComment();
            baseChartImg.src = url;
            setStatus('Chart generated.', 'var(--success)');
        } catch (e) {
            if (e.name !== 'AbortError') setStatus('Error: ' + e.message, 'red');
        }
    }

    function renderWithComment() {
        if (!baseChartImg) return;

        const comment = elComment.value.trim();
        const w = baseChartImg.naturalWidth;
        const h = baseChartImg.naturalHeight;

        const canvas = document.createElement('canvas');
        canvas.width  = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(baseChartImg, 0, 0);

        if (comment) {
            const panelX  = w * 0.67;
            const panelW  = w - panelX;
            const boxX    = panelX + panelW * 0.04;
            const boxW    = panelW * 0.88;
            const boxY    = h * 0.50;   // mitad inferior del panel
            const boxH    = h * 0.94 - boxY;
            const padY    = 10;
            const maxTW   = boxW - 20;

            let fontSize, lines;
            for (fontSize = Math.round(w * 0.030); fontSize >= Math.round(w * 0.009); fontSize--) {
                ctx.font = `italic ${fontSize}px Inter, sans-serif`;
                const lh = fontSize * 1.45;
                const words = comment.split(' ');
                lines = [];
                let line = '';
                for (const word of words) {
                    const test = line ? `${line} ${word}` : word;
                    if (ctx.measureText(test).width > maxTW && line) {
                        lines.push(line);
                        line = word;
                    } else {
                        line = test;
                    }
                }
                if (line) lines.push(line);
                if (lines.length * lh + padY * 2 <= boxH) break;
            }

            const lh = fontSize * 1.45;
            const totalH = lines.length * lh;
            let ty = boxY + padY + (boxH - padY * 2 - totalH) / 2;

            ctx.fillStyle = '#E0E0E0';
            ctx.font = `italic ${fontSize}px Inter, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            for (const l of lines) {
                ctx.fillText(l, boxX + boxW / 2, ty);
                ty += lh;
            }
        }

        canvas.toBlob(blob => {
            currentChartBlob = blob;
            chartImg.src = URL.createObjectURL(blob);
            chartImg.style.display = 'block';
            chartPH.style.display  = 'none';
        }, 'image/png');
    }

    // ── Share ─────────────────────────────────────────────────────────────────

    async function shareWhatsApp() {
        if (!currentChartBlob) {
            setStatus('Please generate chart first.', 'red');
            return;
        }
        if (!navigator.share) {
            const url = URL.createObjectURL(currentChartBlob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'spread.png';
            a.click();
            setStatus('Image downloaded. Share it manually.', 'var(--primary)');
            return;
        }
        try {
            const file = new File([currentChartBlob], 'spread_chart.png', { type: 'image/png' });
            await navigator.share({ title: 'Spread Operation', files: [file] });
            setStatus('Shared successfully!', 'var(--success)');
        } catch (e) {
            if (e.name !== 'AbortError') setStatus('Share cancelled.', 'var(--text-muted)');
        }
    }

    // ── Event listeners ───────────────────────────────────────────────────────

    elStrategy.addEventListener('change', resetForm);

    elExp.addEventListener('change', autoCalcCredit);
    elComment.addEventListener('input', renderWithComment);
    btnRefresh.addEventListener('click', loadMarketData);
    btnShare.addEventListener('click', shareWhatsApp);

    // ── Init ──────────────────────────────────────────────────────────────────

    renderStrikes('PCS');
    loadMarketData();
});
