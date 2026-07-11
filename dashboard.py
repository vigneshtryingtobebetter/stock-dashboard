"""
dashboard_v6.py
Universal Stock Screener + Portfolio + Indicators + Email Alerts + Theme Toggle + Comparison + PDF Export.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time
import requests
import smtplib
from email.mime.text import MIMEText

from data_fetcher import fetch_current_price, fetch_historical
from database import init_database, save_price, get_recent_prices

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Screener Pro v6",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT UNIVERSE
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "NFLX", "AMD", "INTC",
    "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "PYPL", "SQ", "COIN",
    "JNJ", "PFE", "UNH", "ABBV", "MRK", "LLY", "TMO", "ABT",
    "XOM", "CVX", "COP", "GE", "BA", "CAT", "DE",
    "WMT", "COST", "HD", "KO", "PEP", "MCD", "SBUX", "NKE", "LULU",
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "ARKK", "XLF", "XLK", "XLE",
    "BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD",
    "BABA", "TSM", "SONY", "SAP", "ASML", "TM", "NIO", "JD",
    "GME", "AMC", "PLTR", "RIVN", "LCID", "SPCE",
]

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if 'universe' not in st.session_state:
    st.session_state.universe = DEFAULT_UNIVERSE.copy()

if 'favorites' not in st.session_state:
    st.session_state.favorites = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]

if 'alerts' not in st.session_state:
    st.session_state.alerts = []

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

if 'sent_emails' not in st.session_state:
    st.session_state.sent_emails = set()  # NEW: dedup email alerts

if 'theme' not in st.session_state:
    st.session_state.theme = "Dark"

# ─────────────────────────────────────────────────────────────────────────────
# THEME TOGGLE (NEW)
# ─────────────────────────────────────────────────────────────────────────────
def apply_theme():
    """Injects CSS for Light mode. Streamlit defaults to dark."""
    if st.session_state.theme == "Light":
        st.markdown("""
        <style>
        .stApp { background-color: #f8f9fa !important; color: #212529 !important; }
        .stMetric { background-color: #ffffff; border-radius: 8px; padding: 8px; }
        .stDataFrame { background-color: #ffffff; }
        </style>
        """, unsafe_allow_html=True)
        return "plotly_white"
    return "plotly_dark"

# ─────────────────────────────────────────────────────────────────────────────
# INDICATORS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().sort_values('datetime')

    for w in [5, 20]:
        df[f'SMA_{w}'] = df['close'].rolling(window=w, min_periods=1).mean()

    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=14, min_periods=1).mean()
    avg_loss = loss.rolling(window=14, min_periods=1).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    df['BB_Middle'] = df['close'].rolling(window=20, min_periods=1).mean()
    rolling_std = df['close'].rolling(window=20, min_periods=1).std()
    df['BB_Upper'] = df['BB_Middle'] + (2 * rolling_std)
    df['BB_Lower'] = df['BB_Middle'] - (2 * rolling_std)
    df['BB_Width'] = df['BB_Upper'] - df['BB_Lower']
    df['BB_PercentB'] = (df['close'] - df['BB_Lower']) / df['BB_Width']

    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema_12 - ema_26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    return df


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def fetch_universe_snapshot(symbols: list) -> pd.DataFrame:
    records = []
    prog = st.progress(0, text="Fetching market data...")
    for i, sym in enumerate(symbols):
        try:
            d = fetch_current_price(sym)
            records.append({
                'Symbol': d['symbol'], 'Price': d['price'],
                'Change': d['change'], 'Change %': d['change_percent'],
                'Prev Close': d['previous_close'], 'Timestamp': d['timestamp']
            })
            save_price(d)
        except Exception:
            pass
        prog.progress((i + 1) / len(symbols), text=f"Loading {sym}...")
        time.sleep(0.12)
    prog.empty()
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# S&P 500 SCRAPER
# ─────────────────────────────────────────────────────────────────────────────

def scrape_sp500() -> list:
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        r = requests.get(url, timeout=15)
        tables = pd.read_html(r.text)
        tickers = tables[0]['Symbol'].tolist()
        return [t.replace('.', '-') for t in tickers]
    except Exception as e:
        st.error(f"Scraper failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# PORTFOLIO LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def calculate_portfolio() -> pd.DataFrame:
    if not st.session_state.portfolio:
        return pd.DataFrame()
    rows = []
    for pos in st.session_state.portfolio:
        try:
            data = fetch_current_price(pos['symbol'])
            price = data['price']
            shares = pos['shares']
            avg_cost = pos['avg_cost']
            mv = shares * price
            cb = shares * avg_cost
            pnl = mv - cb
            pnl_pct = (pnl / cb) * 100 if cb else 0
            rows.append({
                'Symbol': pos['symbol'], 'Shares': shares, 'Avg Cost': avg_cost,
                'Current': price, 'Market Value': round(mv, 2),
                'Cost Basis': round(cb, 2), 'P&L $': round(pnl, 2), 'P&L %': round(pnl_pct, 2)
            })
        except Exception:
            pass
        time.sleep(0.1)
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL ALERTS (NEW)
# ─────────────────────────────────────────────────────────────────────────────

def send_email(subject: str, body: str, cfg: dict) -> bool:
    """Sends email via SMTP. Returns True on success."""
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = cfg['sender']
        msg['To'] = cfg['recipient']

        with smtplib.SMTP_SSL(cfg['server'], cfg['port']) as server:
            server.login(cfg['sender'], cfg['password'])
            server.sendmail(cfg['sender'], cfg['recipient'], msg.as_string())
        return True
    except Exception as e:
        st.sidebar.error(f"Email error: {e}")
        return False


def check_alerts_and_email(symbol: str, current_price: float, smtp_cfg: dict):
    """Checks alerts, shows toast, and sends email (max once per trigger)."""
    for alert in st.session_state.alerts:
        if alert['symbol'] != symbol:
            continue

        triggered = False
        if alert['condition'] == 'above' and current_price > alert['price']:
            triggered = True
        elif alert['condition'] == 'below' and current_price < alert['price']:
            triggered = True

        if triggered:
            alert_key = f"{symbol}_{alert['condition']}_{alert['price']}"
            st.toast(f"🚨 {symbol} {alert['condition']} ${alert['price']}! Now ${current_price}")

            # Send email only if not already sent for this alert
            if alert_key not in st.session_state.sent_emails and smtp_cfg.get('sender'):
                body = (f"Stock Alert Triggered!\n\n"
                        f"Symbol: {symbol}\n"
                        f"Condition: Price went {alert['condition']} ${alert['price']}\n"
                        f"Current Price: ${current_price}\n"
                        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                if send_email(f"Alert: {symbol}", body, smtp_cfg):
                    st.session_state.sent_emails.add(alert_key)
                    st.sidebar.success(f"Email sent for {symbol}!")


# ─────────────────────────────────────────────────────────────────────────────
# PDF EXPORT (NEW)
# ─────────────────────────────────────────────────────────────────────────────

from fpdf import FPDF

def generate_portfolio_pdf(portfolio_df: pd.DataFrame) -> bytes:
    """Generates a PDF report from portfolio DataFrame."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Portfolio Report", ln=True, align="C")
    pdf.ln(5)

    if portfolio_df.empty:
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, "No positions found.", ln=True)
    else:
        total_val = portfolio_df['Market Value'].sum()
        total_cost = portfolio_df['Cost Basis'].sum()
        total_pnl = total_val - total_cost

        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Summary", ln=True)
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"Total Value: ${total_val:,.2f}", ln=True)
        pdf.cell(0, 10, f"Total Cost:  ${total_cost:,.2f}", ln=True)
        pdf.cell(0, 10, f"Total P&L:   ${total_pnl:,.2f}", ln=True)
        pdf.ln(5)

        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Holdings", ln=True)
        pdf.set_font("Arial", "", 10)

        for _, row in portfolio_df.iterrows():
            line = (f"{row['Symbol']}: {row['Shares']} shares | "
                    f"Current ${row['Current']} | "
                    f"P&L ${row['P&L $']} ({row['P&L %']}%)")
            pdf.cell(0, 8, line, ln=True)

    return bytes(pdf.output())


# ─────────────────────────────────────────────────────────────────────────────
# UI COMPONENTS
# ─────────────────────────────────────────────────────────────────────────────

def display_favorites(smtp_cfg: dict, chart_theme: str):
    st.subheader("⭐ Favorites")
    cols = st.columns(min(len(st.session_state.favorites), 5))
    for idx, sym in enumerate(st.session_state.favorites):
        try:
            data = fetch_current_price(sym)
            save_price(data)
            with cols[idx % 5]:
                color = "normal" if data['change'] >= 0 else "inverse"
                st.metric(
                    label=sym, value=f"${data['price']:.2f}",
                    delta=f"{data['change']:.2f} ({data['change_percent']}%)",
                    delta_color=color
                )
                check_alerts_and_email(sym, data['price'], smtp_cfg)
        except Exception:
            with cols[idx % 5]:
                st.metric(label=sym, value="N/A", delta="--")


def display_portfolio():
    st.subheader("💼 Portfolio Tracker")

    with st.expander("➕ Add Position", expanded=False):
        with st.form("portfolio_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                p_sym = st.text_input("Symbol", placeholder="AAPL").upper().strip()
            with c2:
                p_shares = st.number_input("Shares", min_value=0.0, value=10.0, step=1.0)
            with c3:
                p_cost = st.number_input("Avg Cost ($)", min_value=0.0, value=100.0, step=1.0)
            if st.form_submit_button("Add Position") and p_sym:
                st.session_state.portfolio.append({
                    'symbol': p_sym, 'shares': p_shares, 'avg_cost': p_cost
                })
                st.success(f"Added {p_sym}")
                time.sleep(0.3)
                st.rerun()

    port_df = calculate_portfolio()
    if not port_df.empty:
        total_val = port_df['Market Value'].sum()
        total_cost = port_df['Cost Basis'].sum()
        total_pnl = total_val - total_cost
        total_pnl_pct = (total_pnl / total_cost) * 100 if total_cost else 0

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Value", f"${total_val:,.2f}")
        m2.metric("Total Cost", f"${total_cost:,.2f}")
        m3.metric("Total P&L", f"${total_pnl:,.2f}", f"{total_pnl_pct:.2f}%")

        def color_pnl(val):
            color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
            return f'color: {color}; font-weight: bold'

        styled = port_df.style.map(color_pnl, subset=['P&L $', 'P&L %'])
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # NEW: PDF Export
        pdf_bytes = generate_portfolio_pdf(port_df)
        st.download_button("📄 Download PDF Report", pdf_bytes, "portfolio_report.pdf", mime="application/pdf")

        to_remove = st.multiselect("Remove positions", port_df['Symbol'].tolist())
        if st.button("🗑️ Remove Selected") and to_remove:
            st.session_state.portfolio = [p for p in st.session_state.portfolio if p['symbol'] not in to_remove]
            st.rerun()
    else:
        st.info("No positions yet. Add your first stock above.")


def display_screener_table(df: pd.DataFrame):
    st.subheader(f"🌍 Market Screener ({len(df)} assets)")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        search = st.text_input("🔍 Search", "").upper()
    with c2:
        min_c = st.number_input("Min Change %", value=-50.0, step=1.0)
    with c3:
        max_c = st.number_input("Max Change %", value=50.0, step=1.0)

    if search:
        df = df[df['Symbol'].str.contains(search)]
    df = df[(df['Change %'] >= min_c) & (df['Change %'] <= max_c)]
    df = df.sort_values('Change %', ascending=False)

    def color_change(val):
        color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
        return f'color: {color}; font-weight: bold'

    styled = df.style.map(color_change, subset=['Change %'])
    st.dataframe(styled, use_container_width=True, height=500)
    return st.selectbox("📈 Select for chart", df['Symbol'].tolist())


def display_chart(symbol: str, chart_theme: str):
    st.divider()
    st.subheader(f"{symbol} — Technical Analysis")

    hist = fetch_historical(symbol, period="3mo")
    if hist.empty or len(hist) < 26:
        st.warning("Need 26+ data points for MACD.")
        return

    hist = add_indicators(hist)
    x = hist['datetime'] if 'datetime' in hist.columns else hist['date']

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.5, 0.25, 0.25],
        subplot_titles=(f"{symbol} Price", "RSI (14)", "MACD")
    )

    # Price + BB + SMA
    fig.add_trace(go.Candlestick(
        x=x, open=hist['open'], high=hist['high'],
        low=hist['low'], close=hist['close'], name="Price"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(x=x, y=hist['BB_Upper'], mode='lines',
        name='BB Upper', line=dict(color='rgba(255,255,255,0.3)')), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=hist['BB_Lower'], mode='lines',
        name='BB Lower', line=dict(color='rgba(255,255,255,0.3)'),
        fill='tonexty', fillcolor='rgba(100,100,255,0.08)'), row=1, col=1)

    fig.add_trace(go.Scatter(x=x, y=hist['SMA_5'], mode='lines',
        name='SMA 5', line=dict(color='orange')), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=hist['SMA_20'], mode='lines',
        name='SMA 20', line=dict(color='cyan')), row=1, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=x, y=hist['RSI'], mode='lines',
        name='RSI', line=dict(color='purple'), showlegend=False), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    # MACD
    colors = ['green' if h >= 0 else 'red' for h in hist['MACD_Hist']]
    fig.add_trace(go.Bar(x=x, y=hist['MACD_Hist'], marker_color=colors,
        name='MACD Hist', showlegend=False), row=3, col=1)
    fig.add_trace(go.Scatter(x=x, y=hist['MACD'], mode='lines',
        name='MACD', line=dict(color='blue')), row=3, col=1)
    fig.add_trace(go.Scatter(x=x, y=hist['MACD_Signal'], mode='lines',
        name='Signal', line=dict(color='red')), row=3, col=1)
    fig.add_hline(y=0, line_dash="solid", line_color="gray", row=3, col=1)

    fig.update_layout(template=chart_theme, height=900, hovermode="x unified")
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)

    latest = hist.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        rsi = latest['RSI']
        if rsi > 70: st.error(f"RSI: {rsi:.1f} 🔴")
        elif rsi < 30: st.success(f"RSI: {rsi:.1f} 🟢")
        else: st.info(f"RSI: {rsi:.1f} ⚪")
    with c2:
        st.metric("BB Width", f"{latest['BB_Width']:.2f}")
    with c3:
        st.metric("%B", f"{latest['BB_PercentB']:.2f}")
    with c4:
        macd_sig = "Bullish" if latest['MACD'] > latest['MACD_Signal'] else "Bearish"
        st.metric("MACD Signal", macd_sig)


# ─────────────────────────────────────────────────────────────────────────────
# SIDE-BY-SIDE COMPARISON (NEW)
# ─────────────────────────────────────────────────────────────────────────────

def display_comparison(chart_theme: str):
    st.divider()
    st.subheader("⚖️ Side-by-Side Comparison")

    c1, c2 = st.columns(2)
    with c1:
        s1 = st.selectbox("Stock A", st.session_state.universe, key="comp_a")
        hist1 = fetch_historical(s1, period="1mo")
        if not hist1.empty:
            fig1 = go.Figure()
            fig1.add_trace(go.Scatter(
                x=hist1['datetime'] if 'datetime' in hist1.columns else hist1['date'],
                y=hist1['close'], mode='lines', name=s1, line=dict(color='cyan')
            ))
            fig1.update_layout(title=f"{s1} Price", template=chart_theme, height=350, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig1, use_container_width=True, key="chart_a")

    with c2:
        s2 = st.selectbox("Stock B", st.session_state.universe, key="comp_b")
        hist2 = fetch_historical(s2, period="1mo")
        if not hist2.empty:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=hist2['datetime'] if 'datetime' in hist2.columns else hist2['date'],
                y=hist2['close'], mode='lines', name=s2, line=dict(color='orange')
            ))
            fig2.update_layout(title=f"{s2} Price", template=chart_theme, height=350, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig2, use_container_width=True, key="chart_b")


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

def sidebar():
    st.sidebar.header("🎨 Appearance")
    theme_choice = st.sidebar.selectbox("Theme", ["Dark", "Light"], index=0 if st.session_state.theme == "Dark" else 1)
    st.session_state.theme = theme_choice

    st.sidebar.divider()

    # NEW: Email SMTP Config
    st.sidebar.header("📧 Email Alerts")
    with st.sidebar.expander("SMTP Settings"):
        smtp_server = st.text_input("SMTP Server", "smtp.gmail.com", key="smtp_srv")
        smtp_port = st.number_input("Port", value=465, key="smtp_port")
        sender = st.text_input("Sender Email", key="smtp_from")
        password = st.text_input("App Password", type="password", key="smtp_pw")
        recipient = st.text_input("Recipient Email", key="smtp_to")

        smtp_cfg = {
            'server': smtp_server, 'port': int(smtp_port),
            'sender': sender, 'password': password, 'recipient': recipient
        }

        if st.button("Send Test Email", key="smtp_test"):
            if sender and password and recipient:
                if send_email("Stock Alert Test", "Your alert system is working!", smtp_cfg):
                    st.sidebar.success("Test email sent!")
            else:
                st.sidebar.warning("Fill all fields first.")

        if st.button("Clear Sent History", key="clr_email"):
            st.session_state.sent_emails.clear()
            st.sidebar.success("Cleared!")

    st.sidebar.divider()

    # Universe Manager
    st.sidebar.header("🌍 Universe")
    new_sym = st.sidebar.text_input("Add Symbol", placeholder="e.g., RELIANCE.NS").upper().strip()
    if st.sidebar.button("➕ Add") and new_sym:
        if new_sym not in st.session_state.universe:
            st.session_state.universe.append(new_sym)
            st.rerun()

    # CSV Import
    uploaded = st.sidebar.file_uploader("Upload CSV", type=['csv'])
    if uploaded:
        try:
            csv_df = pd.read_csv(uploaded)
            sym_col = None
            for col in ['symbol', 'Symbol', 'ticker', 'Ticker']:
                if col in csv_df.columns:
                    sym_col = col
                    break
            if sym_col:
                new_syms = csv_df[sym_col].str.upper().str.strip().tolist()
                added = sum(1 for s in new_syms if s and s not in st.session_state.universe)
                st.session_state.universe.extend([s for s in new_syms if s and s not in st.session_state.universe])
                st.sidebar.success(f"Added {added} symbols!")
                st.rerun()
            else:
                st.sidebar.error("Need 'symbol' column")
        except Exception as e:
            st.sidebar.error(f"CSV error: {e}")

    # S&P 500
    if st.sidebar.button("🌐 Import S&P 500"):
        with st.sidebar.status("Scraping..."):
            sp500 = scrape_sp500()
            if sp500:
                added = sum(1 for s in sp500 if s not in st.session_state.universe)
                st.session_state.universe.extend([s for s in sp500 if s not in st.session_state.universe])
                st.sidebar.success(f"Added {added} S&P 500 stocks!")
                st.rerun()

    st.sidebar.divider()

    # Favorites
    st.sidebar.header("⭐ Favorites")
    fav_add = st.sidebar.selectbox("Pin symbol", st.session_state.universe)
    if st.sidebar.button("📌 Pin"):
        if fav_add not in st.session_state.favorites:
            st.session_state.favorites.append(fav_add)
            st.rerun()

    if st.session_state.favorites:
        rem = st.sidebar.multiselect("Unpin", st.session_state.favorites)
        if st.sidebar.button("🗑️ Unpin") and rem:
            for r in rem:
                if r in st.session_state.favorites:
                    st.session_state.favorites.remove(r)
            st.rerun()

    st.sidebar.divider()
    st.sidebar.caption(f"Universe: {len(st.session_state.universe)} | Favorites: {len(st.session_state.favorites)}")

    # Return SMTP config for use in main
    return smtp_cfg if (sender and password and recipient) else {}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    init_database()

    st.title("🌍 Stock Screener Pro v6")
    st.caption("SMA · RSI · Bollinger · MACD | Portfolio | Email Alerts | Theme | Comparison | PDF")

    # Apply theme and get chart template
    chart_theme = apply_theme()

    # Sidebar returns SMTP config if filled
    smtp_cfg = sidebar()

    # Fetch universe
    df = fetch_universe_snapshot(st.session_state.universe)
    if df.empty:
        st.error("No market data. Check connection.")
        return

    # Layout
    display_favorites(smtp_cfg, chart_theme)
    st.divider()
    display_portfolio()
    st.divider()
    display_comparison(chart_theme)
    st.divider()
    selected = display_screener_table(df)
    display_chart(selected, chart_theme)

    # Export
    st.divider()
    with st.expander("📥 Export Data"):
        st.download_button("Download Snapshot CSV", df.to_csv(index=False), "market.csv")


if __name__ == "__main__":
    main()
