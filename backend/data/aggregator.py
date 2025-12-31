
"""
Data Aggregator
Downloads optimal available history for D1, H1, and M15.
Storage: backend/data/
"""
import yfinance as yf
import pandas as pd
import os

# Define Max Possible Limits for Yahoo Finance
TIMEFRAMES = {
    "1d": "max",     # Goes back to ~2000
    "1h": "730d",    # Max 2 years
    "15m": "60d",    # Max 60 days
}

def download_all():
    print("📦 GIA Data Aggregator Starting...")
    
    base_dir = "backend/data/cache"
    os.makedirs(base_dir, exist_ok=True)
    
    tickers = ["GC=F", "XAUUSD=X"]
    
    for interval, period in TIMEFRAMES.items():
        print(f"\n📡 Fetching {interval} (Limit: {period})...")
        success = False
        
        for symbol in tickers:
            try:
                print(f"   Trying {symbol}...")
                df = yf.download(symbol, period=period, interval=interval, progress=False)
                
                if not df.empty:
                    # Clean
                    df = df.reset_index()
                    df.columns = [c.lower() for c in df.columns]
                    
                    # Normalize Date col
                    if 'date' not in df.columns and 'datetime' not in df.columns:
                        df = df.rename(columns={df.columns[0]: 'date'})
                    elif 'datetime' in df.columns:
                         df = df.rename(columns={'datetime': 'date'})

                    # Save
                    filename = f"{base_dir}/gold_data_{interval}.csv"
                    df.to_csv(filename, index=False)
                    print(f"   ✅ Saved {len(df)} rows to {filename}")
                    success = True
                    break # Stop trying tickers for this interval
            except Exception as e:
                print(f"   ⚠️ Error: {e}")
                
        if not success:
            print(f"   ❌ Failed to fetch {interval} data.")

if __name__ == "__main__":
    download_all()
