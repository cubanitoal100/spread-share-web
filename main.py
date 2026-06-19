import customtkinter as ctk
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import numpy as np
import urllib.parse
import webbrowser
import win32clipboard
import yfinance as yf
from io import BytesIO
from PIL import Image
import threading
import textwrap

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class SpreadApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Spread Share")
        self.geometry("1000x750")
        self.minsize(850, 550) # Límite lógico de tamaño mínimo

        # Configurar colores
        self.bg_color = "#0A1128"
        self.text_color = "white"

        # Frame Izquierdo: Controles (Ahora Scrollable para pantallas pequeñas)
        self.frame_inputs = ctk.CTkScrollableFrame(self, width=330)
        self.frame_inputs.pack(side="left", fill="y", padx=10, pady=10)

        ctk.CTkLabel(self.frame_inputs, text="Parámetros del Spread", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)

        # Tipo de Spread
        ctk.CTkLabel(self.frame_inputs, text="Tipo de Spread:").pack(anchor="w", padx=15)
        self.spread_type = ctk.CTkOptionMenu(self.frame_inputs, values=["CCS (Call Credit Spread)", "PCS (Put Credit Spread)"])
        self.spread_type.pack(pady=5, padx=15, fill="x")

        # Fecha de Expiración
        ctk.CTkLabel(self.frame_inputs, text="Fecha de Expiración:").pack(anchor="w", padx=15, pady=(5,0))
        self.expiration_menu = ctk.CTkOptionMenu(self.frame_inputs, values=["Buscando..."], command=self.on_strike_key)
        self.expiration_menu.pack(pady=5, padx=15, fill="x")

        # Short Strike
        ctk.CTkLabel(self.frame_inputs, text="Strike Vendido (Short):").pack(anchor="w", padx=15, pady=(10,0))
        self.short_strike = ctk.CTkEntry(self.frame_inputs, placeholder_text="Ej: 7500")
        self.short_strike.pack(pady=5, padx=15, fill="x")

        # Long Strike
        ctk.CTkLabel(self.frame_inputs, text="Strike Comprado (Long):").pack(anchor="w", padx=15, pady=(10,0))
        self.long_strike = ctk.CTkEntry(self.frame_inputs, placeholder_text="Ej: 7520")
        self.long_strike.pack(pady=5, padx=15, fill="x")

        # Eventos para calcular automáticamente mientras se escribe (con retraso de 800ms)
        self.short_strike.bind("<KeyRelease>", self.on_strike_key)
        self.long_strike.bind("<KeyRelease>", self.on_strike_key)
        self._strike_timer = None

        # Net Credit
        ctk.CTkLabel(self.frame_inputs, text="Crédito Neto / Prima:").pack(anchor="w", padx=15, pady=(10,0))
        self.net_credit = ctk.CTkEntry(self.frame_inputs, placeholder_text="Ej: 10 (Se calcula auto)")
        self.net_credit.pack(pady=5, padx=15, fill="x")

        # Current Price
        ctk.CTkLabel(self.frame_inputs, text="Precio Actual SPX:").pack(anchor="w", padx=15, pady=(10,0))
        frame_spx = ctk.CTkFrame(self.frame_inputs, fg_color="transparent")
        frame_spx.pack(fill="x", padx=15, pady=5)
        
        self.current_price = ctk.CTkEntry(frame_spx, placeholder_text="Buscando...")
        self.current_price.pack(side="left", fill="x", expand=True)
        
        btn_spx = ctk.CTkButton(frame_spx, text="Actualizar", width=60, command=self.fetch_spx_price_thread)
        btn_spx.pack(side="right", padx=(5,0))

        # Comentario para WhatsApp
        ctk.CTkLabel(self.frame_inputs, text="Comentario (WhatsApp):").pack(anchor="w", padx=15, pady=(10,0))
        self.txt_comment = ctk.CTkTextbox(self.frame_inputs, height=80)
        self.txt_comment.pack(pady=5, padx=15, fill="x")

        # Botones
        self.btn_calc = ctk.CTkButton(self.frame_inputs, text="Calcular y Graficar", command=self.update_chart)
        self.btn_calc.pack(pady=20, padx=15, fill="x")

        self.btn_share = ctk.CTkButton(self.frame_inputs, text="Compartir en WhatsApp", command=self.share_whatsapp, fg_color="#25D366", hover_color="#128C7E", text_color="white", font=ctk.CTkFont(weight="bold"))
        self.btn_share.pack(pady=5, padx=15, fill="x")

        # Etiqueta de estado
        self.lbl_status = ctk.CTkLabel(self.frame_inputs, text="", text_color="yellow", wraplength=250)
        self.lbl_status.pack(pady=20, padx=15)

        # Frame Derecho: Gráfica
        self.frame_chart = ctk.CTkFrame(self, fg_color=self.bg_color)
        self.frame_chart.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        # Preparar Figura de Matplotlib
        self.fig, self.ax = plt.subplots(figsize=(8, 5), facecolor=self.bg_color)
        self.ax.set_facecolor(self.bg_color)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame_chart)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        
        self.draw_empty_chart()
        self.metrics = {}
        
        # Buscar mercado en segundo plano al iniciar
        self.fetch_spx_price_thread()

    def fetch_spx_price_thread(self):
        self.lbl_status.configure(text="Conectando al mercado...", text_color="yellow")
        threading.Thread(target=self._fetch_market_data, daemon=True).start()

    def _fetch_market_data(self):
        try:
            ticker_spx = yf.Ticker("^SPX")
            expirations = ticker_spx.options
            
            ticker_gspc = yf.Ticker("^GSPC")
            todays_data = ticker_gspc.history(period='1d', interval='1m')
            
            current_price = None
            if not todays_data.empty:
                current_price = todays_data['Close'].iloc[-1]
                
            self.after(0, self._update_market_ui, current_price, expirations)
        except Exception as e:
            self.after(0, lambda: self.lbl_status.configure(text=f"Error de mercado: {e}", text_color="red"))

    def _update_market_ui(self, price, expirations):
        if price:
            self.current_price.delete(0, 'end')
            self.current_price.insert(0, f"{price:.2f}")
            
        if expirations:
            self.expiration_menu.configure(values=list(expirations))
            self.expiration_menu.set(expirations[0]) # 0 DTE por defecto
            
        self.lbl_status.configure(text="Mercado conectado. Fechas y precios listos.", text_color="green")

    def on_strike_key(self, event=None):
        if hasattr(self, '_strike_timer') and self._strike_timer is not None:
            self.after_cancel(self._strike_timer)
        self._strike_timer = self.after(800, self.auto_calc_credit_thread)

    def auto_calc_credit_thread(self):
        k_short = self.get_float(self.short_strike)
        k_long = self.get_float(self.long_strike)
        s_type_full = self.spread_type.get()
        s_type = s_type_full.split()[0]
        exp_date = self.expiration_menu.get()
        
        if not k_short or not k_long or exp_date == "Buscando...":
            return
            
        self.lbl_status.configure(text=f"Buscando crédito para {exp_date}...", text_color="yellow")
        threading.Thread(target=self._fetch_credit, args=(s_type, k_short, k_long, exp_date), daemon=True).start()

    def _fetch_credit(self, s_type, k_short, k_long, exp_date):
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
                self.after(0, lambda: self.lbl_status.configure(text=f"Strikes {k_short} o {k_long} no existen en {exp_date}.", text_color="red"))
                return
                
            short_bid, short_ask = short_opt.iloc[0]['bid'], short_opt.iloc[0]['ask']
            long_bid, long_ask = long_opt.iloc[0]['bid'], long_opt.iloc[0]['ask']
            
            # Fallback a lastPrice si bid y ask son 0 (fuera de horario de mercado)
            if short_bid == 0 and short_ask == 0:
                short_mid = short_opt.iloc[0]['lastPrice']
            else:
                short_mid = (short_bid + short_ask) / 2
                
            if long_bid == 0 and long_ask == 0:
                long_mid = long_opt.iloc[0]['lastPrice']
            else:
                long_mid = (long_bid + long_ask) / 2
            
            net_credit = short_mid - long_mid
            
            self.after(0, self._update_credit_ui, net_credit)
        except Exception as e:
            self.after(0, lambda: self.lbl_status.configure(text=f"Error obteniendo opciones: {e}", text_color="red"))
            
    def _update_credit_ui(self, credit):
        self.net_credit.delete(0, 'end')
        self.net_credit.insert(0, f"{credit:.2f}")
        self.lbl_status.configure(text="Crédito calculado automáticamente.", text_color="green")
        self.update_idletasks()

    def draw_empty_chart(self):
        self.ax.clear()
        self.ax.set_facecolor(self.bg_color)
        self.ax.tick_params(colors=self.text_color)
        self.ax.spines['bottom'].set_color(self.text_color)
        self.ax.spines['top'].set_color('none') 
        self.ax.spines['right'].set_color('none')
        self.ax.spines['left'].set_color(self.text_color)
        self.ax.axhline(0, color='gray', linewidth=1)
        self.fig.tight_layout()
        self.canvas.draw()

    def get_float(self, entry):
        try:
            val = entry.get().replace(",", ".")
            return float(val) if val else None
        except ValueError:
            return None

    def update_chart(self):
        s_type_full = self.spread_type.get()
        s_type = s_type_full.split()[0] # "CCS" o "PCS"
        k_short = self.get_float(self.short_strike)
        k_long = self.get_float(self.long_strike)
        credit = self.get_float(self.net_credit)
        current = self.get_float(self.current_price)

        if None in (k_short, k_long, credit):
            self.lbl_status.configure(text="Por favor ingresa Short, Long y Crédito.", text_color="red")
            return

        self.ax.clear()
        self.ax.set_facecolor(self.bg_color)

        # Determinar rango del eje X
        margin = abs(k_long - k_short) * 2.5
        min_p = min(k_short, k_long) - margin
        max_p = max(k_short, k_long) + margin
        prices = np.linspace(min_p, max_p, 1000)

        # Calcular PnL
        if s_type == "CCS":
            short_pnl = np.minimum(0, k_short - prices)
            long_pnl = np.maximum(0, prices - k_long)
            pnl = short_pnl + long_pnl + credit
            max_profit = credit
            max_loss = (k_long - k_short) - credit
            breakeven = k_short + credit
        else: # PCS
            short_pnl = np.minimum(0, prices - k_short)
            long_pnl = np.maximum(0, k_long - prices)
            pnl = short_pnl + long_pnl + credit
            max_profit = credit
            max_loss = (k_short - k_long) - credit
            breakeven = k_short - credit

        # Línea de PnL y línea cero
        self.ax.axhline(0, color='gray', linewidth=1)
        self.ax.plot(prices, pnl, color='white', linewidth=2)
        
        # Crear degradado suave con capas de alpha
        z_pos = np.maximum(0, pnl)
        z_neg = np.minimum(0, pnl)
        
        y_max = np.max(z_pos)
        if y_max > 0:
            for i in np.linspace(0, 1, 40):
                self.ax.fill_between(prices, z_pos * i, z_pos, color='#00FF00', alpha=0.03, linewidth=0)
                
        y_min = np.min(z_neg)
        if y_min < 0:
            for i in np.linspace(0, 1, 40):
                self.ax.fill_between(prices, z_neg, z_neg * i, color='#FF0000', alpha=0.03, linewidth=0)

        # Líneas verticales de Strikes
        self.ax.axvline(k_short, color='white', linestyle='--', alpha=0.4)
        self.ax.text(k_short, y_min * 1.05, f' {k_short}', color='white', alpha=0.7, va='top', ha='center', fontsize=9)
        
        self.ax.axvline(k_long, color='white', linestyle='--', alpha=0.4)
        self.ax.text(k_long, y_min * 1.05, f' {k_long}', color='white', alpha=0.7, va='top', ha='center', fontsize=9)

        # Precio actual
        if current:
            self.ax.axvline(current, color='#00BFFF', linestyle='-', linewidth=1.5)
            self.ax.text(current, y_max * 1.05, f'{current}', color='#00BFFF', va='bottom', ha='center', fontweight='bold')

        # Formateo visual
        title_text = f"NET CREDIT: ${credit:.2f}     MAX LOSS: ${max_loss:.2f}     MAX PROFIT: ${max_profit:.2f}     BREAKEVEN: {breakeven:.2f}"
        self.ax.set_title(title_text, color='white', fontsize=11, fontweight='bold', pad=15)

        self.ax.tick_params(colors=self.text_color)
        self.ax.spines['bottom'].set_color(self.text_color)
        self.ax.spines['top'].set_color('none') 
        self.ax.spines['right'].set_color('none')
        self.ax.spines['left'].set_color(self.text_color)
        self.ax.yaxis.set_major_formatter('${x:1.0f}')
        
        # Agregar Textos Grandes Profesionales en la gráfica
        bbox_props = dict(boxstyle="round,pad=0.3", fc=self.bg_color, ec="none", alpha=0.8)
        
        if s_type == "CCS":
            op_name = "CALL CREDIT SPREAD"
            # CCS: Ganancia izq, vacío a la derecha
            x_pos = 0.95
            align = "right"
        else:
            op_name = "PUT CREDIT SPREAD"
            # PCS: Ganancia der, vacío a la izquierda
            x_pos = 0.05
            align = "left"
            
        # Posición adaptada para no estorbar y letras mucho más grandes
        self.ax.text(x_pos, 0.95, op_name, color="white", fontsize=24, fontweight="heavy", ha=align, va="top", transform=self.ax.transAxes, bbox=bbox_props)
        self.ax.text(x_pos, 0.85, f"SELL - {k_short}", color="#FF4444", fontsize=28, fontweight="bold", ha=align, va="top", transform=self.ax.transAxes, bbox=bbox_props)
        self.ax.text(x_pos, 0.72, f"BUY - {k_long}", color="#00FF00", fontsize=28, fontweight="bold", ha=align, va="top", transform=self.ax.transAxes, bbox=bbox_props)
        
        # Incrustar comentario en la parte inferior si existe
        comment = self.txt_comment.get("1.0", "end-1c").strip()
        if comment:
            wrapped_comment = "\n".join(textwrap.wrap(comment, width=80))
            self.fig.text(0.5, 0.08, wrapped_comment, color="#E0E0E0", fontsize=14, fontstyle="italic", ha="center", va="center", bbox=dict(boxstyle="round,pad=0.5", fc="#16213E", ec="#00BFFF", alpha=0.9))
            self.fig.tight_layout(rect=[0, 0.18, 1, 1])
        else:
            self.fig.tight_layout()
            
        self.canvas.draw()
        
        self.metrics = {
            "type": s_type,
            "short": k_short,
            "long": k_long,
            "credit": credit,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "breakeven": breakeven,
            "current": current
        }
        self.lbl_status.configure(text="Gráfica actualizada correctamente.", text_color="green")

    def copy_image_to_clipboard(self):
        # Guardar gráfico en memoria
        buf = BytesIO()
        self.fig.savefig(buf, format='png', facecolor=self.bg_color, edgecolor='none', dpi=120)
        buf.seek(0)
        
        # Usar PIL para convertir PNG a formato compatible con portapapeles Windows (DIB/BMP)
        img = Image.open(buf)
        output = BytesIO()
        img.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:] # Extraer el body del BMP omitiendo la cabecera
        
        # Enviar al portapapeles de Windows
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()

    def share_whatsapp(self):
        if not self.metrics:
            self.lbl_status.configure(text="Calcula la gráfica primero.", text_color="red")
            return
            
        try:
            self.lbl_status.configure(text="Generando imagen y abriendo WhatsApp...", text_color="yellow")
            self.update()
            
            # Refrescar la gráfica por si se agregó un comentario nuevo
            self.update_chart()
            
            # 1. Copiar al portapapeles
            self.copy_image_to_clipboard()
            
            # 2. Enviar solo un espacio como texto ya que todo está en la imagen
            text = " "
            
            # 3. Abrir WhatsApp
            encoded_text = urllib.parse.quote(text)
            url = f"https://wa.me/?text={encoded_text}"
            webbrowser.open(url)
            
            self.lbl_status.configure(text="¡Listo! Ve a WhatsApp y presiona Ctrl+V para pegar la gráfica.", text_color="#25D366")
        except Exception as e:
            self.lbl_status.configure(text=f"Error: {e}", text_color="red")

if __name__ == "__main__":
    app = SpreadApp()
    app.mainloop()
