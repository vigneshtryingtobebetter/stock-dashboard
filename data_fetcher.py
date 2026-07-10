"""
data_fetcher.py
Robust stock data fetcher with multiple fallback strategies.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime


def fetch_current_price(symbol: str) -> dict:
    """
    Fetches current stock price with multiple fallback strategies.
    Works even when market is closed or API returns incomplete data.
    """
    
    # Validate symbol
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("Please enter a valid stock symbol (e.g., AAPL)")
    
    ticker = yf.Ticker(symbol)
    
    # Strategy 1: Try ticker.info (most common)
    info = ticker.info or {}
    
    current_price = info.get('currentPrice')
    previous_close = info.get('previousClose')
    
    # Strategy 2: Fallback to regularMarket fields
    if current_price is None:
        current_price = info.get('regularMarketPrice')
    if previous_close is None:
        previous_close = info.get('regularMarketPreviousClose')
    
    # Strategy 3: Use historical data if info is empty
    if current_price is None:
        hist = ticker.history(period="5d")
        if not hist.empty:
            current_price = float(hist['Close'].iloc[-1])
            # Previous close is the day before last
            if len(hist) > 1:
                previous_close = float(hist['Close'].iloc[-2])
            else:
                previous_close = current_price
        else:
            raise ValueError(f"No data found for '{symbol}'. Check the symbol and try again.")
    
    # Ensure we have a previous_close for change calculation
    if previous_close is None:
        previous_close = current_price
    
    # Calculate changes
    change = current_price - previous_close
    change_percent = (change / previous_close * 100) if previous_close != 0 else 0
    
    return {
        'symbol': symbol,
        'price': round(float(current_price), 2),
        'previous_close': round(float(previous_close), 2),
        'change': round(float(change), 2),
        'change_percent': round(float(change_percent), 2),
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }


def fetch_historical(symbol: str, period: str = "1d") -> pd.DataFrame:
    """
    Fetches historical OHLCV data.
    """
    ticker = yf.Ticker(symbol.strip().upper())
    hist = ticker.history(period=period)
    
    if hist.empty:
        return pd.DataFrame()
    
    hist = hist.reset_index()
    
    # Handle both 'Date' and 'Datetime' column names
    if 'Date' in hist.columns:
        hist = hist.rename(columns={'Date': 'datetime'})
    elif 'Datetime' in hist.columns:
        hist = hist.rename(columns={'Datetime': 'datetime'})
    
    hist = hist.rename(columns={
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close',
        'Volume': 'volume'
    })
    
    return hist


# Test it!
if __name__ == "__main__":
    print("Testing data fetcher...")
    
    try:
        # Test with Apple
        data = fetch_current_price("AAPL")
        print(f"\n✅ SUCCESS: {data}")
        
        # Test historical
        hist = fetch_historical("AAPL", period="5d")
        print(f"\nHistorical data shape: {hist.shape}")
        print(hist.head())
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
