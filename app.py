import os
import io
import time
import numpy as np
import requests
from flask import Flask, render_template, request, jsonify, send_file
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from flask_cors import CORS

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')
CORS(app)

TRADIER_TOKEN = os.environ.get("TRADIER_TOKEN")
TRADIER_BASE = "https://api.tradier.com/v1"
CACHE_TTL = 300

_options_cache = {}

def _headers():
    return {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json"
    }

def _get_float(val):
    try:
        return float(val)
    except Exception:
        return None

def _get_options_chain(symbol, exp_date):
    cache_key = f"{symbol}:{exp_date}"
    now = time.time()
    if cache_key in _options_cache:
        ts, opts = _options_cache[cache_key]
        if now - ts < CACHE_TTL:
            return opts
    r = requests.get(
        f"{TRADIER_BASE}/markets/options/chains",
        params={"symbol": symbol, "expiration": exp_date, "greeks": "false"},
        headers=_headers(),
        timeout=10
    )
    r.raise_for_status()
    opts = r.json()["options"]["option"]
    _options_cache[cache_key] = (now, opts)
    return opts

def _mid(opt):
    bid = opt.get("bid") or 0
    ask = opt.get("ask") or 0
    if bid == 0 and ask == 0:
        return opt.get("last") or 0
    return (bid + ask) / 2

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/market_data')
def market_data():
    symbol = request.args.get('symbol', 'SPX').upper().strip()
    try:
        r = requests.get(
            f"{TRADIER_BASE}/markets/quotes",
            params={"symbols": symbol},
            headers=_headers(),
            timeout=10
        )
        r.raise_for_status()
        current_price = r.json()["quotes"]["quote"]["last"]

        exp_params = {"symbol": symbol, "strikes": "false"}
        if symbol in ("SPX", "SPXW"):
            exp_params["includeAllRoots"] = "true"

        r = requests.get(
            f"{TRADIER_BASE}/markets/options/expirations",
            params=exp_params,
            headers=_headers(),
            timeout=10
        )
        r.raise_for_status()
        dates = r.json()["expirations"]["date"]
        expirations = [dates] if isinstance(dates, str) else list(dates)

        return jsonify({"current_price": current_price, "expirations": expirations})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/calculate_credit', methods=['POST'])
def calculate_credit():
    data = request.json
    strategy = data.get('strategy')
    symbol = data.get('symbol', 'SPX').upper().strip()
    exp_date = data.get('exp_date')
    strikes = data.get('strikes', {})

    if not strategy or not exp_date:
        return jsonify({"error": "Missing parameters"}), 400

    try:
        opts = _get_options_chain(symbol, exp_date)

        def find(strike, opt_type):
            o = next((o for o in opts
                      if abs(o["strike"] - float(strike)) < 0.01 and o["option_type"] == opt_type), None)
            if not o:
                raise ValueError(f"Strike {strike} {opt_type} not found for {exp_date}")
            return o

        if strategy == 'PCS':
            net = _mid(find(strikes['k_short'], 'put')) - _mid(find(strikes['k_long'], 'put'))
        elif strategy == 'CCS':
            net = _mid(find(strikes['k_short'], 'call')) - _mid(find(strikes['k_long'], 'call'))
        elif strategy == 'IC':
            net = (_mid(find(strikes['put_sell'], 'put')) - _mid(find(strikes['put_buy'], 'put'))
                   + _mid(find(strikes['call_sell'], 'call')) - _mid(find(strikes['call_buy'], 'call')))
        elif strategy == 'IB':
            net = (_mid(find(strikes['body'], 'put')) + _mid(find(strikes['body'], 'call'))
                   - _mid(find(strikes['put_buy'], 'put')) - _mid(find(strikes['call_buy'], 'call')))
        elif strategy == 'CSP':
            net = _mid(find(strikes['k_short'], 'put'))
        elif strategy == 'CC':
            net = _mid(find(strikes['k_short'], 'call'))
        elif strategy == 'JL':
            net = (_mid(find(strikes['put_sell'], 'put'))
                   + _mid(find(strikes['call_sell'], 'call'))
                   - _mid(find(strikes['call_buy'], 'call')))
        else:
            return jsonify({"error": "Unknown strategy"}), 400

        return jsonify({"net_credit": round(net, 2)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate_chart', methods=['POST'])
def generate_chart():
    data = request.json
    strategy  = data.get('strategy')
    symbol    = data.get('symbol', 'SPX').upper().strip()
    strikes   = data.get('strikes', {})
    net_credit = _get_float(data.get('net_credit'))
    current_price = _get_float(data.get('current_price'))

    if not strategy or not strikes or net_credit is None:
        return jsonify({"error": "Missing parameters"}), 400

    fv = {k: float(v) for k, v in strikes.items() if v not in (None, '', 0)}
    if not fv:
        return jsonify({"error": "No strikes provided"}), 400

    def sp(k, p): return -np.maximum(k - p, 0)
    def lp(k, p): return  np.maximum(k - p, 0)
    def sc(k, p): return -np.maximum(p - k, 0)
    def lc(k, p): return  np.maximum(p - k, 0)

    STRATEGY_NAMES = {
        'PCS': 'PUT CREDIT SPREAD',
        'CCS': 'CALL CREDIT SPREAD',
        'IC':  'IRON CONDOR',
        'IB':  'IRON BUTTERFLY',
        'CSP': 'CASH SECURED PUT',
        'CC':  'COVERED CALL',
        'JL':  'JADE LIZARD',
    }

    min_k, max_k = min(fv.values()), max(fv.values())
    span = max(max_k - min_k, 50)

    if strategy == 'PCS':
        k_s, k_l = fv['k_short'], fv['k_long']
        prices = np.linspace(k_s - span * 1.5, k_s + span * 0.5, 500)
        pnl = net_credit + sp(k_s, prices) + lp(k_l, prices)
        max_profit = net_credit
        max_loss   = k_s - k_l - net_credit
        be_str     = f"{k_s - net_credit:.2f}"
        legs = [("SELL PUT", k_s, "#FF4444"), ("BUY PUT", k_l, "#00FF00")]

    elif strategy == 'CCS':
        k_s, k_l = fv['k_short'], fv['k_long']
        prices = np.linspace(k_s - span * 0.5, k_l + span * 1.5, 500)
        pnl = net_credit + sc(k_s, prices) + lc(k_l, prices)
        max_profit = net_credit
        max_loss   = k_l - k_s - net_credit
        be_str     = f"{k_s + net_credit:.2f}"
        legs = [("SELL CALL", k_s, "#FF4444"), ("BUY CALL", k_l, "#00FF00")]

    elif strategy == 'IC':
        pb, ps, cs, cb = fv['put_buy'], fv['put_sell'], fv['call_sell'], fv['call_buy']
        prices = np.linspace(pb - span * 0.5, cb + span * 0.5, 500)
        pnl = net_credit + sp(ps, prices) + lp(pb, prices) + sc(cs, prices) + lc(cb, prices)
        max_profit = net_credit
        max_loss   = max(ps - pb, cb - cs) - net_credit
        be_str     = f"{ps - net_credit:.2f} / {cs + net_credit:.2f}"
        legs = [("BUY PUT", pb, "#00FF00"), ("SELL PUT", ps, "#FF4444"),
                ("SELL CALL", cs, "#FF4444"), ("BUY CALL", cb, "#00FF00")]

    elif strategy == 'IB':
        pb, body, cb = fv['put_buy'], fv['body'], fv['call_buy']
        prices = np.linspace(pb - span * 0.5, cb + span * 0.5, 500)
        pnl = net_credit + sp(body, prices) + lp(pb, prices) + sc(body, prices) + lc(cb, prices)
        max_profit = net_credit
        max_loss   = min(body - pb, cb - body) - net_credit
        be_str     = f"{body - net_credit:.2f} / {body + net_credit:.2f}"
        legs = [("BUY PUT", pb, "#00FF00"), ("SELL ATM", body, "#FF4444"), ("BUY CALL", cb, "#00FF00")]

    elif strategy == 'CSP':
        k_s = fv['k_short']
        prices = np.linspace(max(0, k_s * 0.6), k_s * 1.2, 500)
        pnl = net_credit + sp(k_s, prices)
        max_profit = net_credit
        max_loss   = k_s - net_credit
        be_str     = f"{k_s - net_credit:.2f}"
        legs = [("SELL PUT", k_s, "#FF4444")]

    elif strategy == 'CC':
        k_s = fv['k_short']
        s0  = current_price or k_s
        prices = np.linspace(max(0, s0 * 0.6), k_s * 1.2, 500)
        pnl = (prices - s0) + net_credit + sc(k_s, prices)
        max_profit = k_s - s0 + net_credit
        max_loss   = s0 - net_credit
        be_str     = f"{s0 - net_credit:.2f}"
        legs = [("SELL CALL", k_s, "#FF4444")]

    elif strategy == 'JL':
        ps, cs, cb = fv['put_sell'], fv['call_sell'], fv['call_buy']
        prices = np.linspace(max(0, ps * 0.7), cb * 1.15, 500)
        pnl = net_credit + sp(ps, prices) + sc(cs, prices) + lc(cb, prices)
        max_profit = net_credit
        cw = cb - cs
        max_loss   = max(ps - net_credit, max(cw - net_credit, 0))
        be_str     = f"{ps - net_credit:.2f}"
        legs = [("SELL PUT", ps, "#FF4444"), ("SELL CALL", cs, "#FF4444"), ("BUY CALL", cb, "#00FF00")]

    else:
        return jsonify({"error": "Unknown strategy"}), 400

    # --- Draw chart ---
    bg = "#0A1128"
    fig, ax = plt.subplots(figsize=(11, 8), facecolor=bg)
    ax.set_facecolor(bg)

    ax.plot(prices, pnl, color='white', linewidth=2)
    ax.axhline(0, color='gray', linewidth=1, alpha=0.5)

    pm = pnl > 0
    if np.any(pm):
        for i in range(10):
            ax.fill_between(prices, 0, np.where(pm, pnl * (1 - i/10.0), 0),
                            where=pm, color=(0, 0.8, 0), alpha=0.1, zorder=1)

    lm = pnl < 0
    if np.any(lm):
        for i in range(10):
            ax.fill_between(prices, np.where(lm, pnl * (1 - i/10.0), 0), 0,
                            where=lm, color=(0.8, 0, 0), alpha=0.1, zorder=1)

    for label, k, color in legs:
        is_sell = 'SELL' in label
        ax.axvline(k, color='#00BFFF' if is_sell else 'gray',
                   linestyle='-' if is_sell else '--', linewidth=1.5)

    ax.tick_params(colors='white')
    for spine in ('top', 'right'):
        ax.spines[spine].set_color('none')
    ax.spines['bottom'].set_color('white')
    ax.spines['left'].set_color('white')
    ax.yaxis.set_major_formatter('${x:1.0f}')

    title = f"NET CREDIT: ${net_credit:.2f}    MAX LOSS: ${abs(max_loss):.2f}    BREAKEVEN: {be_str}"
    ax.set_title(title, color='white', pad=15, fontsize=12, fontweight='bold')

    fig.subplots_adjust(left=0.07, right=0.63, top=0.91, bottom=0.08)

    # Vertical separator
    fig.add_artist(Line2D([0.66, 0.66], [0.05, 0.97], transform=fig.transFigure,
                          color='white', linewidth=0.5, alpha=0.2))
    # Horizontal separator — divides info (top) from comment (bottom)
    fig.add_artist(Line2D([0.67, 0.995], [0.50, 0.50], transform=fig.transFigure,
                          color='white', linewidth=0.5, alpha=0.2))

    # --- Right panel (top half: 0.93 → 0.51) ---
    px = 0.68
    n  = len(legs)

    # Font sizes adaptive to number of legs in the half-panel
    num_fs   = 24 if n <= 2 else (20 if n == 3 else 16)
    label_fs = 12 if n <= 2 else (11 if n == 3 else  9)

    op_name = STRATEGY_NAMES.get(strategy, strategy)
    fig.text(px, 0.93, op_name, color="white", fontsize=11, fontweight="heavy",
             ha="left", va="top", transform=fig.transFigure,
             bbox=dict(boxstyle="round,pad=0.4", fc=bg, ec="#00BFFF", linewidth=1.5))

    # Ticker — same size as numbers
    fig.text(px, 0.83, symbol, color="#00BFFF", fontsize=num_fs, fontweight="bold",
             ha="left", va="top", transform=fig.transFigure)

    # Legs — constrained to top half (0.71 → 0.51)
    legs_top = 0.71
    legs_bot = 0.51

    if strategy == 'IC':
        # 2×2 grid: put spread on top row, call spread on bottom row
        # legs order: [BUY PUT, SELL PUT, SELL CALL, BUY CALL]
        px_l, px_r = 0.68, 0.835
        nf, lf = 22, 11
        rows = [
            (0.71, 0.61, legs[0], legs[1]),  # top: BUY PUT | SELL PUT
            (0.61, 0.51, legs[2], legs[3]),  # bot: SELL CALL | BUY CALL
        ]
        for yt, yb, leg_l, leg_r in rows:
            sh = yt - yb
            for (label, k, color), col_x in ((leg_l, px_l), (leg_r, px_r)):
                fig.text(col_x, yt, label, color=color, fontsize=lf, fontweight="bold",
                         ha="left", va="top", transform=fig.transFigure)
                fig.text(col_x, yt - sh * 0.42, f"{k:g}", color=color, fontsize=nf, fontweight="bold",
                         ha="left", va="top", transform=fig.transFigure,
                         bbox=dict(boxstyle="round,pad=0.3", fc=bg, ec=color, linewidth=1.5))
    else:
        slot_h = (legs_top - legs_bot) / n
        for i, (label, k, color) in enumerate(legs):
            y_lbl = legs_top - i * slot_h
            y_num = y_lbl - slot_h * 0.40
            fig.text(px, y_lbl, label, color=color, fontsize=label_fs, fontweight="bold",
                     ha="left", va="top", transform=fig.transFigure)
            fig.text(px, y_num, f"{k:g}", color=color, fontsize=num_fs, fontweight="bold",
                     ha="left", va="top", transform=fig.transFigure,
                     bbox=dict(boxstyle="round,pad=0.3", fc=bg, ec=color, linewidth=1.5))

    img_io = io.BytesIO()
    fig.savefig(img_io, format='png', facecolor=bg, bbox_inches='tight')
    img_io.seek(0)
    plt.close(fig)
    return send_file(img_io, mimetype='image/png')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
