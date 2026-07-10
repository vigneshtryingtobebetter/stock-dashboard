"""
dashboard_v2.py
Multi-stock watchlist with technical indicators (Moving Averages).
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

from data_fetcher import fetch_current_price, fetch_historical
from database import init_database, save_price, get_recent_prices, get_all_symbols


# Page configuration
st.set_page_config(
    page_title="Real-Time Stock Dashboard Pro",
    page_icon="📈",
    layout="wide"
)

# Initialize session state for watchlist
if 'watchlist' not in st.session_state:
    st.session_state.watchlist = ["AAPL", "MSFT", "GOOGL"]

if 'alerts' not in st.session_state:
    st.session_state.alerts = []


def add_moving_averages(df: pd.DataFrame, windows=[5, 20]) -> pd.DataFrame:
    """
    Calculates Simple Moving Averages (SMA) for given window periods.
    Pure pandas - no ta-lib needed!
    """
    df = df.copy()
    df = df.sort_values('date' if 'date' in df.columns else 'datetime')
    
    for window in windows:
        col_name = f'SMA_{window}'
        df[col_name] = df['close'].rolling(window=window, min_periods=1).mean()
    
    return df


def display_watchlist():
    """Shows all watched stocks in a grid of metric cards."""
    st.subheader("👀 Watchlist")
    
    cols = st.columns(len(st.session_state.watchlist))
    
    for idx, symbol in enumerate(st.session_state.watchlist):
        try:
            data = fetch_current_price(symbol)
            
            # Save to DB
            save_price(data)
            
            with cols[idx]:
                delta_color = "normal" if data['change'] >= 0 else "inverse"
                st.metric(
                    label=symbol,
                    value=f"${data['price']:.2f}",
                    delta=f"{data['change']:.2f} ({data['change_percent']}%)",
                    delta_color=delta_color
                )
                
                # Check alerts
                check_alerts(symbol, data['price'])
                
        except Exception as e:
            with cols[idx]:
                st.error(f"{symbol}: Error")


def check_alerts(symbol: str, current_price: float):
    """Checks if any user-defined alert thresholds are triggered."""
    for alert in st.session_state.alerts:
        if alert['symbol'] == symbol:
            if alert['condition'] == 'above' and current_price > alert['price']:
                st.toast(f"🚨 {symbol} is above ${alert['price']}! Now ${current_price}", icon="🚀")
            elif alert['condition'] == 'below' and current_price < alert['price']:
                st.toast(f"🚨 {symbol} is below ${alert['price']}! Now ${current_price}", icon="📉")


def display_detailed_chart(symbol: str):
    """Shows candlestick chart with SMA lines."""
    st.subheader(f"📊 {symbol} Technical Chart")
    
    # Get 1 month of data for better MA lines
    hist = fetch_historical(symbol, period="1mo")
    
    if hist.empty:
        st.warning("No historical data.")
        return
    
    # Add moving averages
    hist = add_moving_averages(hist, windows=[5, 20])
    
    fig = go.Figure()
    
    # Candlesticks
    x_col = 'date' if 'date' in hist.columns else 'datetime'
    fig.add_trace(go.Candlestick(
        x=hist[x_col],
        open=hist['open'],
        high=hist['high'],
        low=hist['low'],
        close=hist['close'],
        name="Price"
    ))
    
    # SMA 5 (fast)
    fig.add_trace(go.Scatter(
        x=hist[x_col],
        y=hist['SMA_5'],
        mode='lines',
        name='SMA 5 (Fast)',
        line=dict(color='orange', width=1.5)
    ))
    
    # SMA 20 (slow)
    fig.add_trace(go.Scatter(
        x=hist[x_col],
        y=hist['SMA_20'],
        mode='lines',
        name='SMA 20 (Slow)',
        line=dict(color='blue', width=1.5)
    ))
    
    fig.update_layout(
        title=f"{symbol} - Price + Moving Averages",
        yaxis_title="Price ($)",
        template="plotly_dark",
        height=500,
        xaxis_rangeslider_visible=False
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Explain the indicators
    with st.expander("ℹ️ What are these lines?"):
        st.markdown("""
        - **SMA 5 (Orange)**: 5-period average. Follows price closely. Good for short-term trends.
        - **SMA 20 (Blue)**: 20-period average. Smoother line. Good for medium-term trends.
        - **Golden Cross**: When SMA 5 crosses *above* SMA 20 = bullish signal.
        - **Death Cross**: When SMA 5 crosses *below* SMA 20 = bearish signal.
        """)


def sidebar_controls():
    """Sidebar for managing watchlist and alerts."""
    st.sidebar.header("⚙️ Watchlist Manager")
    
    # Add new symbol
    new_symbol = st.sidebar.text_input("Add Symbol", placeholder="e.g., TSLA").upper().strip()
    if st.sidebar.button("➕ Add to Watchlist") and new_symbol:
        if new_symbol not in st.session_state.watchlist:
            st.session_state.watchlist.append(new_symbol)
            st.sidebar.success(f"Added {new_symbol}!")
            st.rerun()
        else:
            st.sidebar.warning("Already in watchlist.")
    
    # Remove symbol
    if len(st.session_state.watchlist) > 1:
        to_remove = st.sidebar.selectbox("Remove Symbol", st.session_state.watchlist)
        if st.sidebar.button("➖ Remove"):
            st.session_state.watchlist.remove(to_remove)
            st.rerun()
    
    st.sidebar.divider()
    
    # Alert Manager
    st.sidebar.header("🚨 Price Alerts")
    alert_sym = st.sidebar.selectbox("Symbol", st.session_state.watchlist)
    alert_price = st.sidebar.number_input("Target Price ($)", min_value=0.0, value=100.0, step=1.0)
    alert_condition = st.sidebar.radio("Condition", ["above", "below"])
    
    if st.sidebar.button("Set Alert"):
        st.session_state.alerts.append({
            'symbol': alert_sym,
            'price': alert_price,
            'condition': alert_condition
        })
        st.sidebar.success(f"Alert set: {alert_sym} {alert_condition} ${alert_price}")
    
    if st.session_state.alerts:
        st.sidebar.write("Active Alerts:")
        for i, alert in enumerate(st.session_state.alerts):
            st.sidebar.caption(f"{i+1}. {alert['symbol']} {alert['condition']} ${alert['price']}")


def main():
    init_database()
    
    st.title("📈 Real-Time Stock Dashboard Pro")
    st.markdown("Multi-stock watchlist with technical indicators.")
    
    sidebar_controls()
    
    # Auto-refresh
    auto_refresh = st.checkbox("🔄 Auto-refresh every 60s", value=True)
    
    # Display watchlist grid
    display_watchlist()
    
    st.divider()
    
    # Detailed view for selected symbol
    selected = st.selectbox("Select symbol for detailed view", st.session_state.watchlist)
    display_detailed_chart(selected)
    
    # Raw data table
    st.divider()
    with st.expander("🔍 View Collected Data"):
        recent = get_recent_prices(selected, limit=50)
        st.dataframe(recent, use_container_width=True)
    
    # Auto-refresh
    if auto_refresh:
        import time
        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    main()