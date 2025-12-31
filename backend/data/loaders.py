"""
Data Loaders - Price & News Fetchers
"""
# import yfinance as yf # STRICTLY REMOVED FOR OFFLINE MODE
import pandas as pd
import requests
import os
from datetime import datetime
from pathlib import Path

# Paths relative to project root
BASE_DIR = Path(__file__).parent.parent.parent
CACHE_DIR = BASE_DIR / "backend"

def fetch_real_gold_data(period="max", interval="1d"):
    """
    CRITICAL: Strictly Offline Mode. 
    Loads data ONLY from backend/hestory via load_history_data.
    Standardizes output for the rest of the system.
    """
    print(f"📂 fetch_real_gold_data called for {interval}...")
    
    # Map '1h' -> 'H1', '15m' -> 'M15', '1d' -> 'H1' (Fallback or Error?)
    # The user only provided M1, M15, M30, H1. D1 is not in list.
    # If D1 requested, we might need to Resample H1 or Error. 
    # For now, let's map best effort.
    
    tf_map = {
        "1h": "H1", "60m": "H1", "H1": "H1",
        "30m": "M30", "M30": "M30",
        "15m": "M15", "M15": "M15",
        "1m": "M1", "M1": "M1"
    }
    
    target_tf = tf_map.get(interval, "H1") # Default H1 if unknown
    
    print(f"   ℹ️  Mapping {interval} -> {target_tf} (Local Source)")
    
    # Delegate to the new robust loader
    df = load_history_data(timeframe=target_tf)
    
    if df is None or df.empty:
        print("❌ CRITICAL: No local data found in backend/hestory.")
        print("   System operates in OFFLINE MODE only.")
        return None
        
    print(f"   ✅ Using LOCAL cTrader data ({len(df)} rows)")
    
    # The system expects 'date', 'open', 'high', 'low', 'close', 'volume'
    # load_history_data provides these (lowercase).
    
    # Date Filtering based on Period?
    # 'max' = return all.
    # '1y', '2y' = filter last X years?
    # Simple logic used previously was yfinance period.
    # Here we just return full history unless refactored.
    # The caller (processor) handles slicing usually, OR we slice here.
    
    if period != "max":
        # Rough slicing if needed, but processor usually handles logic.
        # Let's just return full valid data.
        pass
        
    return df

def fetch_real_gold_news(api_key="demo"):
    """Fetches world economic news related to gold."""
    print("📡 Fetching news sentiment...")
    url = f'https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers=XAU&apikey={api_key}'
    try:
        r = requests.get(url)
        data = r.json()
        if "feed" not in data: return None
        
        news = []
        for item in data["feed"]:
            time_str = item["time_published"]
            date_obj = datetime.strptime(time_str, '%Y%m%dT%H%M%S')
            
            score = float(item["overall_sentiment_score"])
            sentiment = 1 if score > 0.15 else (-1 if score < -0.15 else 0)
            
            # Find Gold relevance
            relevance = 0
            for t in item.get("ticker_sentiment", []):
                if t["ticker"] == "XAU":
                    relevance = float(t["relevance_score"])
                    break
            
            news.append({
                "date": date_obj.strftime('%Y-%m-%d'),
                "sentiment": sentiment,
                "impact": "HIGH" if relevance > 0.7 else ("MEDIUM" if relevance > 0.3 else "LOW")
            })
        return pd.DataFrame(news)
    except: return None

def load_history_data(timeframe="H1", start_year=None, end_year=None):
    """
    Loads historical data from backend/hestory
    Timeframe options: M1, M15, M30, H1
    """
    file_map = {
        "M1": "XAUUSD_M1.csv",
        "M15": "XAUUSD_M15.csv",
        "M30": "XAUUSD_M30.csv",
        "H1": "XAUUSD_H1.csv"
    }
    
    filename = file_map.get(timeframe, "XAUUSD_H1.csv")
    path = CACHE_DIR / "hestory" / filename
    
    # NEW STABLE LOCAL PATH (Bypassing OneDrive)
    local_path = Path(rf"C:\GIA_DATA\{filename}")
    if local_path.exists():
        path = local_path
            
    if not path.exists():
        print(f"❌ History file not found: {path}")
        return None
        
    print(f"📂 Loading History: {path.absolute()}")
    try:
        # Standard Format encountered: 10/1/2010 12:00:00 AM
        df = pd.read_csv(path)
        df.columns = [c.capitalize() for c in df.columns]
        
        # Parse Dates
        df['Date'] = pd.to_datetime(df['Time'], format='%m/%d/%Y %I:%M:%S %p')
        df = df.drop(columns=['Time'])
        
        # Filter Years
        if start_year:
            df = df[df['Date'].dt.year >= int(start_year)]
        if end_year:
            df = df[df['Date'].dt.year <= int(end_year)]
            
        # Clean
        df = df.sort_values('Date').reset_index(drop=True)
        # Rename for internal consistency (lowercase)
        df.columns = [c.lower() for c in df.columns]
        
        return df
    except Exception as e:
        print(f"❌ Error loading history: {e}")
        return None
