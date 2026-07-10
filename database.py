"""
database.py
Handles all database operations.
SQLite is perfect for this - it's just a file, no setup needed.
"""

import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path


# The database file name
DB_FILE = "stock_data.db"


def get_connection():
    """Creates a connection to our SQLite database."""
    return sqlite3.connect(DB_FILE)


def init_database():
    """
    Creates the tables we need if they don't exist.
    Run this once when starting the app.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create table for storing price snapshots
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            price REAL NOT NULL,
            previous_close REAL,
            change REAL,
            change_percent REAL,
            timestamp TEXT NOT NULL
        )
    """)
    
    # Create index for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_symbol_time 
        ON price_history(symbol, timestamp)
    """)
    
    conn.commit()
    conn.close()
    print("✅ Database initialized!")


def save_price(data: dict):
    """
    Saves a price snapshot to the database.
    
    Parameters:
        data (dict): The dictionary from fetch_current_price()
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO price_history 
        (symbol, price, previous_close, change, change_percent, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        data['symbol'],
        data['price'],
        data['previous_close'],
        data['change'],
        data['change_percent'],
        data['timestamp']
    ))
    
    conn.commit()
    conn.close()


def get_recent_prices(symbol: str, limit: int = 100) -> pd.DataFrame:
    """
    Retrieves recent prices for a symbol.
    
    Parameters:
        symbol (str): Stock ticker
        limit (int): How many records to return
    
    Returns:
        DataFrame: Recent price records
    """
    conn = get_connection()
    
    query = """
        SELECT * FROM price_history 
        WHERE symbol = ? 
        ORDER BY timestamp DESC 
        LIMIT ?
    """
    
    df = pd.read_sql_query(query, conn, params=(symbol, limit))
    conn.close()
    
    # Convert timestamp to datetime for plotting
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    return df


def get_all_symbols() -> list:
    """Returns list of all symbols we've tracked."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT symbol FROM price_history")
    symbols = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return symbols


# Test it!
if __name__ == "__main__":
    init_database()
    
    # Test save
    test_data = {
        'symbol': 'AAPL',
        'price': 175.50,
        'previous_close': 174.00,
        'change': 1.50,
        'change_percent': 0.86,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    save_price(test_data)
    print("✅ Test data saved!")
    
    # Test retrieve
    recent = get_recent_prices('AAPL')
    print(f"\nRecent prices:\n{recent}")