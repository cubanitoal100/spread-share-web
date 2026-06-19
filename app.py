import os
import io
import numpy as np
import requests
from flask import Flask, render_template, request, jsonify, send_file
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask_cors import CORS

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')
CORS(app)

TRADIER_TOKEN = os.environ.get("TRADIER_TOKEN")
TRADIER_BASE = "https://api.tradier.com/v1"
CACHE_TTL = 300  # segundos — cadena de opciones válida 5 min

_options_cache = {}  # exp_date → (timestamp, [opciones])

def _headers():
    return {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json"
    }

def _get_float(val):
    try:
        return float(val)
    except:
        return None

def _get_options_chain(exp_date):
    import time
    now = time.time()
    if exp_date in _options_cache:
        ts, opts = _options_cache[exp_date]
        if now - ts < CACHE_TTL:
            return opts
    r = requests.get(
        f"{TRADIER_BASE}/markets/options/chains",
        params={"symbol": "SPX", "expiration": exp_date, "greeks": "false"},
        headers=_headers(),
        timeout=10
    )
    r.raise_for_status()
    opts = r.json()["options"]["option"]
    _options_cache[exp_date] = (now, opts)
    return opts

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/market_data')
def market_data():
    try:
        r = requests.get(
            f"{TRADIER_BASE}/markets/quotes",
            params={"symbols": "SPX"},
            headers=_headers(),
            timeout=10
        )
        r.raise_for_status()
        current_price = r.json()["quotes"]["quote"]["last"]

        r = requests.get(
            f"{TRADIER_BASE}/markets/options/expirations",
            params={"symbol": "SPX", "includeAllRoots": "true", "strikes": "false"},
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
    s_type = data.get('s_type')
    k_short = _get_float(data.get('k_short'))
    k_long = _get_float(data.get('k_long'))
    exp_date = data.get('exp_date')

    if not all([s_type, k_short, k_long, exp_date]):
        return jsonify({"error": "Missing parameters"}), 400

    try:
        opts = _get_options_chain(exp_date)
        opt_type = "call" if s_type == "CCS" else "put"
        short_opt = next((o for o in opts if o["strike"] == k_short and o["option_type"] == opt_type), None)
        long_opt  = next((o for o in opts if o["strike"] == k_long  and o["option_type"] == opt_type), None)

        if not short_opt or not long_opt:
            return jsonify({"error": f"Strikes do not exist in {exp_date}"}), 400

        def mid(opt):
            bid = opt.get("bid") or 0
            ask = opt.get("ask") or 0
            if bid == 0 and ask == 0:
                return opt.get("last") or 0
            return (bid + ask) / 2

        net_credit = mid(short_opt) - mid(long_opt)
        return jsonify({"net_credit": net_credit})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate_chart', methods=['POST'])
def generate_chart():
    data = request.json
    s_type = data.get('s_type')
    k_short = _get_float(data.get('k_short'))
    k_long = _get_float(data.get('k_long'))
    net_credit = _get_float(data.get('net_credit'))

    if not all([s_type, k_short, k_long, net_credit]):
        return jsonify({"error": "Missing parameters"}), 400

    prices = np.linspace(min(k_short, k_long) - 50, max(k_short, k_long) + 50, 500)

    if s_type == "CCS":
        short_pnl = np.where(prices > k_short, k_short - prices, 0)
        long_pnl  = np.where(prices > k_long,  prices - k_long,  0)
        max_loss  = k_long - k_short - net_credit
        breakeven = k_short + net_credit
    else:
        short_pnl = np.where(prices < k_short, prices - k_short, 0)
        long_pnl  = np.where(prices < k_long,  k_long - prices,  0)
        max_loss  = k_short - k_long - net_credit
        breakeven = k_short - net_credit

    pnl = short_pnl + long_pnl + net_credit
    max_profit = net_credit

    bg_color = "#0A1128"
    text_color = "white"
    op_name = "CALL CREDIT SPREAD" if s_type == "CCS" else "PUT CREDIT SPREAD"

    fig, ax = plt.subplots(figsize=(11, 8), facecolor=bg_color)
    ax.set_facecolor(bg_color)

    ax.plot(prices, pnl, color='white', linewidth=2)
    ax.axhline(0, color='gray', linewidth=1, alpha=0.5)

    profit_mask = pnl > 0
    if np.any(profit_mask):
        profit_pnl = np.copy(pnl)
        profit_pnl[~profit_mask] = 0
        for i in range(10):
            y_fill = profit_pnl * (1 - i/10.0)
            ax.fill_between(prices, 0, y_fill, where=profit_mask, color=(0, 0.8, 0), alpha=0.1, zorder=1)

    loss_mask = pnl < 0
    if np.any(loss_mask):
        loss_pnl = np.copy(pnl)
        loss_pnl[~loss_mask] = 0
        for i in range(10):
            y_fill = loss_pnl * (1 - i/10.0)
            ax.fill_between(prices, y_fill, 0, where=loss_mask, color=(0.8, 0, 0), alpha=0.1, zorder=1)

    ax.axvline(k_short, color='#00BFFF', linestyle='-',  linewidth=1.5)
    ax.axvline(k_long,  color='gray',    linestyle='--', linewidth=1.5)

    ax.text(k_short, ax.get_ylim()[1], f"{k_short:g}", color='#00BFFF', ha='center', va='bottom', fontsize=10, fontweight='bold')
    ax.text(k_short, ax.get_ylim()[0], f"{k_short:g}", color='gray',    ha='center', va='top',    fontsize=10)
    ax.text(k_long,  ax.get_ylim()[0], f"{k_long:g}",  color='gray',    ha='center', va='top',    fontsize=10)

    title = f"NET CREDIT: ${max_profit:.2f}    MAX LOSS: ${abs(max_loss):.2f}    BREAKEVEN: {breakeven:.2f}"
    ax.set_title(title, color=text_color, pad=15, fontsize=12, fontweight='bold')

    ax.tick_params(colors=text_color)
    ax.spines['bottom'].set_color(text_color)
    ax.spines['top'].set_color('none')
    ax.spines['right'].set_color('none')
    ax.spines['left'].set_color(text_color)
    ax.yaxis.set_major_formatter('${x:1.0f}')

    # Ajustar el gráfico para dejar panel derecho libre
    fig.subplots_adjust(left=0.07, right=0.63, top=0.91, bottom=0.08)

    # Línea separadora vertical
    from matplotlib.lines import Line2D
    fig.add_artist(Line2D([0.66, 0.66], [0.05, 0.97], transform=fig.transFigure,
                          color='white', linewidth=0.5, alpha=0.2))

    # Panel derecho: tipo de spread
    px = 0.68
    fig.text(px, 0.93, op_name, color="white", fontsize=13, fontweight="heavy",
             ha="left", va="top", transform=fig.transFigure,
             bbox=dict(boxstyle="round,pad=0.4", fc=bg_color, ec="#00BFFF", linewidth=1.5))

    # SELL
    fig.text(px, 0.83, "SELL", color="#FF4444", fontsize=28, fontweight="bold",
             ha="left", va="top", transform=fig.transFigure)
    fig.text(px, 0.73, f"{k_short:g}", color="#FF4444", fontsize=28, fontweight="bold",
             ha="left", va="top", transform=fig.transFigure,
             bbox=dict(boxstyle="round,pad=0.3", fc=bg_color, ec="#FF4444", linewidth=1.5))

    # BUY
    fig.text(px, 0.62, "BUY", color="#00FF00", fontsize=28, fontweight="bold",
             ha="left", va="top", transform=fig.transFigure)
    fig.text(px, 0.52, f"{k_long:g}", color="#00FF00", fontsize=28, fontweight="bold",
             ha="left", va="top", transform=fig.transFigure,
             bbox=dict(boxstyle="round,pad=0.3", fc=bg_color, ec="#00FF00", linewidth=1.5))

    img_io = io.BytesIO()
    fig.savefig(img_io, format='png', facecolor=bg_color, bbox_inches='tight')
    img_io.seek(0)
    plt.close(fig)

    return send_file(img_io, mimetype='image/png')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
