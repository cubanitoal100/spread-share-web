import os
import io
import textwrap
import numpy as np
from flask import Flask, render_template, request, jsonify, send_file
import yfinance as yf
import matplotlib
matplotlib.use('Agg') # Requerido para servidor sin interfaz gráfica
import matplotlib.pyplot as plt
from flask_cors import CORS

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')
CORS(app)

def _get_float(val):
    try:
        return float(val)
    except:
        return None

@app.route('/ping')
def ping():
    return 'ok', 200

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/market_data')
def market_data():
    try:
        ticker = yf.Ticker("^SPX")
        current_price = ticker.history(period="1d")['Close'].iloc[-1]
        expirations = list(ticker.options)
        return jsonify({
            "current_price": current_price,
            "expirations": expirations
        })
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
        ticker = yf.Ticker("^SPX")
        chain = ticker.option_chain(exp_date)
        
        if s_type == "CCS":
            opts = chain.calls
        else: # PCS
            opts = chain.puts
            
        short_opt = opts[opts['strike'] == k_short]
        long_opt = opts[opts['strike'] == k_long]
        
        if short_opt.empty or long_opt.empty:
            return jsonify({"error": f"Strikes do not exist in {exp_date}"}), 400
            
        short_bid, short_ask = short_opt.iloc[0]['bid'], short_opt.iloc[0]['ask']
        long_bid, long_ask = long_opt.iloc[0]['bid'], long_opt.iloc[0]['ask']
        
        if short_bid == 0 and short_ask == 0:
            short_mid = short_opt.iloc[0]['lastPrice']
        else:
            short_mid = (short_bid + short_ask) / 2
            
        if long_bid == 0 and long_ask == 0:
            long_mid = long_opt.iloc[0]['lastPrice']
        else:
            long_mid = (long_bid + long_ask) / 2
        
        net_credit = short_mid - long_mid
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
    comment = data.get('comment', '').strip()
    
    if not all([s_type, k_short, k_long, net_credit]):
        return jsonify({"error": "Missing parameters"}), 400
        
    # Lógica de cálculo de PnL
    prices = np.linspace(min(k_short, k_long) - 50, max(k_short, k_long) + 50, 500)
    
    if s_type == "CCS":
        short_pnl = np.where(prices > k_short, k_short - prices, 0)
        long_pnl = np.where(prices > k_long, prices - k_long, 0)
        max_loss = k_long - k_short - net_credit
        breakeven = k_short + net_credit
    else: # PCS
        short_pnl = np.where(prices < k_short, prices - k_short, 0)
        long_pnl = np.where(prices < k_long, k_long - prices, 0)
        max_loss = k_short - k_long - net_credit
        breakeven = k_short - net_credit
        
    pnl = short_pnl + long_pnl + net_credit
    max_profit = net_credit
    
    # Graficar
    bg_color = "#0A1128"
    text_color = "white"
    fig, ax = plt.subplots(figsize=(8, 8), facecolor=bg_color)
    ax.set_facecolor(bg_color)
    
    ax.plot(prices, pnl, color='white', linewidth=2)
    ax.axhline(0, color='gray', linewidth=1, alpha=0.5)
    
    # Gradientes
    X = np.array([prices, prices])
    Y = np.array([np.zeros(len(prices)), pnl])
    
    profit_mask = pnl > 0
    if np.any(profit_mask):
        profit_pnl = np.copy(pnl)
        profit_pnl[~profit_mask] = 0
        for i in range(10):
            alpha = 1.0 - (i/10.0)
            y_fill = profit_pnl * (1 - i/10.0)
            ax.fill_between(prices, 0, y_fill, where=profit_mask, color=(0, 0.8, 0), alpha=0.1, zorder=1)
            
    loss_mask = pnl < 0
    if np.any(loss_mask):
        loss_pnl = np.copy(pnl)
        loss_pnl[~loss_mask] = 0
        for i in range(10):
            alpha = 1.0 - (i/10.0)
            y_fill = loss_pnl * (1 - i/10.0)
            ax.fill_between(prices, y_fill, 0, where=loss_mask, color=(0.8, 0, 0), alpha=0.1, zorder=1)
    
    ax.axvline(k_short, color='#00BFFF', linestyle='-', linewidth=1.5)
    ax.axvline(k_long, color='gray', linestyle='--', linewidth=1.5)
    
    ax.text(k_short, ax.get_ylim()[1], f"{k_short:g}", color='#00BFFF', ha='center', va='bottom', fontsize=10, fontweight='bold')
    ax.text(k_short, ax.get_ylim()[0], f"{k_short:g}", color='gray', ha='center', va='top', fontsize=10)
    ax.text(k_long, ax.get_ylim()[0], f"{k_long:g}", color='gray', ha='center', va='top', fontsize=10)
    
    title = f"NET CREDIT: ${max_profit:.2f}    MAX LOSS: ${abs(max_loss):.2f}    MAX PROFIT: ${max_profit:.2f}    BREAKEVEN: {breakeven:.2f}"
    ax.set_title(title, color=text_color, pad=20, fontsize=12, fontweight='bold')
    
    ax.tick_params(colors=text_color)
    ax.spines['bottom'].set_color(text_color)
    ax.spines['top'].set_color('none') 
    ax.spines['right'].set_color('none')
    ax.spines['left'].set_color(text_color)
    ax.yaxis.set_major_formatter('${x:1.0f}')
    
    bbox_props = dict(boxstyle="round,pad=0.3", fc=bg_color, ec="none", alpha=0.8)
    
    if s_type == "CCS":
        op_name = "CALL CREDIT SPREAD"
        x_pos = 0.95
        align = "right"
    else:
        op_name = "PUT CREDIT SPREAD"
        x_pos = 0.05
        align = "left"
        
    ax.text(x_pos, 0.95, op_name, color="white", fontsize=24, fontweight="heavy", ha=align, va="top", transform=ax.transAxes, bbox=bbox_props)
    ax.text(x_pos, 0.85, f"SELL - {k_short:g}", color="#FF4444", fontsize=28, fontweight="bold", ha=align, va="top", transform=ax.transAxes, bbox=bbox_props)
    ax.text(x_pos, 0.72, f"BUY - {k_long:g}", color="#00FF00", fontsize=28, fontweight="bold", ha=align, va="top", transform=ax.transAxes, bbox=bbox_props)
    
    if comment:
        wrapped_comment = "\n".join(textwrap.wrap(comment, width=70))
        fig.text(0.5, 0.11, wrapped_comment, color="#E0E0E0", fontsize=18, fontstyle="italic", ha="center", va="center", bbox=dict(boxstyle="round,pad=0.5", fc="#16213E", ec="#00BFFF", alpha=0.9))
        fig.tight_layout(rect=[0, 0.22, 1, 1])
    else:
        fig.tight_layout()
        
    img_io = io.BytesIO()
    fig.savefig(img_io, format='png', facecolor=bg_color, bbox_inches='tight')
    img_io.seek(0)
    plt.close(fig)
    
    return send_file(img_io, mimetype='image/png')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
