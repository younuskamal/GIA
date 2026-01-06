"""
Dataset Processor - Features Engineering & Labeling
"""
import pandas as pd
import numpy as np
import os
from pathlib import Path

import sys
# New Imports
BASE_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_BACKEND not in sys.path:
    sys.path.append(BASE_BACKEND)

from data.loaders import fetch_real_gold_data, fetch_real_gold_news
from data.validator import DataValidator
from utils.indicators import (
    calculate_rsi, calculate_ema, calculate_atr, 
    calculate_macd, calculate_bollinger_bands, calculate_stochastic
)

def build_professional_dataset(period="max", interval="1h"):
    """
    Builds a professional dataset with multi-timeframe synthesized features.
    """
    print(f"🚀 Processing professional dataset [{interval}]...")

    df = fetch_real_gold_data(period=period, interval=interval)
    if df is None or df.empty: return None

    # Labeling: 0.15% threshold (Hyper-Active Mode)
    # We need to force the model to trade, relying on StrategyHandler to filter.
    threshold = 0.0015
    
    return process_raw_data(df)

def process_raw_data(df):
    """
    Applies technical indicators and feature engineering to a raw OHLC DataFrame.
    """
    if df is None or df.empty: return None
    
    # Ensure date is datetime normalized
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        # Drop rows with invalid dates if any
        df = df.dropna(subset=['date'])
        # Ensure it's not timezone-aware for local processing
        if df['date'].dt.tz is not None:
            df['date'] = df['date'].dt.tz_localize(None)
        
    close = df['close']

    # --- Core Indicators ---
    df['rsi'] = calculate_rsi(close, 14)
    df['rsi_slope'] = df['rsi'].diff(3)
    
    # Returns (Pct Change)
    df['ret_1'] = close.pct_change(1)
    df['ret_2'] = close.pct_change(2)
    df['ret_3'] = close.pct_change(3)
    
    # Volatility (Rolling Std of returns)
    df['vol_5'] = df['ret_1'].rolling(5).std()
    df['vol_20'] = df['ret_1'].rolling(20).std()
    
    # --- Multi-Timeframe Synthesized Features ---
    # Adjust horizons based on interval (Assume 1 candle = X minutes)
    # 15m: 1h=4, 1 day=96, 1 week=480, 1 month=2016
    # 1h: 1 day=24, 1 week=120, 1 month=500 (Legacy/Approximation)
    
    # Simple auto-detection of interval based on first two bars
    if len(df) > 1:
        delta = (df['date'].iloc[1] - df['date'].iloc[0]).total_seconds()
        if delta <= 900: # 15m or less
            w_h, m_h = 480, 2016
        else: # 1h or more
            w_h, m_h = 120, 500
    else:
        w_h, m_h = 120, 500

    df['mom_3'] = close.pct_change(3)
    df['mom_5'] = close.pct_change(5)
    # Multi-Timeframe Momentum (Dynamic for M15 alignment)
    # 1 week = 5 days * 24h * 4 candles = 480
    # 1 month = 21 days * 24h * 4 candles = 2016
    df['mom_weekly'] = close.pct_change(480)
    df['mom_monthly'] = close.pct_change(2016)
    
    # --- Price Distances ---
    df['ema_9_dist'] = (close - calculate_ema(close, 9)) / close
    df['ema_21_dist'] = (close - calculate_ema(close, 21)) / close
    df['ema_50_dist'] = (close - calculate_ema(close, 50)) / close
    
    # --- Market Sessions (Institutional Context) ---
    # Gold behavior changes by session.
    df['hour'] = df['date'].dt.hour
    df['is_london'] = ((df['hour'] >= 8) & (df['hour'] <= 16)).astype(int)
    df['is_ny'] = ((df['hour'] >= 13) & (df['hour'] <= 21)).astype(int)
    df['is_asian'] = ((df['hour'] >= 0) & (df['hour'] <= 8)).astype(int)
    
    # --- Volatility & Patterns ---
    df['atr'] = calculate_atr(df, 14)
    df['atr_pct'] = df['atr'] / close
    
    # Intraday Volatility Proxy (Relative Range)
    df['rel_range'] = (df['high'] - df['low']) / df['close']
    
    df['body_size'] = (df['close'] - df['open']) / df['open']
    df['upper_wick'] = (df['high'] - df[['open', 'close']].max(axis=1)) / df['open']
    df['lower_wick'] = (df[['open', 'close']].min(axis=1) - df['low']) / df['open']
    
    # --- Advanced Volatility Squeeze Proxy ---
    upper, _, lower = calculate_bollinger_bands(close, period=20)
    df['bb_width'] = (upper - lower) / close
    
    # --- Advanced ---
    df['macd_norm'], _ = calculate_macd(close)
    df['macd_norm'] = df['macd_norm'] / close
    
    df['bb_pos'] = (close - lower) / (upper - lower + 1e-9)
    
    stoch_k, stoch_d = calculate_stochastic(df)
    df['stoch_k'] = stoch_k
    df['stoch_d'] = stoch_d
    
    # --- Sentiment Integration (Real + Synthetic Proxy) ---
    df['news_sentiment'] = 0
    df['news_impact_score'] = 0
    
    # Synthetic Only for historical backtest usually
    shock_threshold = df['rel_range'].quantile(0.98)
    shock_mask = (df['rel_range'] > shock_threshold)
    
    df.loc[shock_mask, 'news_impact_score'] = 3
    df.loc[shock_mask, 'news_sentiment'] = np.where(df.loc[shock_mask, 'close'] > df.loc[shock_mask, 'open'], 1, -1)

    # --- Labeling (Optional, for Acc Calc) ---
    df['price_change_next'] = df['close'].shift(-1) - df['close']
    df['pct_change_next'] = (df['price_change_next'] / df['close']) * 100
    
    df['label'] = 'WAIT'
    df.loc[df['pct_change_next'] > 0.2, 'label'] = 'BUY'
    df.loc[df['pct_change_next'] < -0.2, 'label'] = 'SELL'
    
    # Final cleanup - Don't drop all NaN, just fill forward and drop remaining in critical columns
    df = df.ffill().bfill()
    critical_cols = ['close', 'rsi', 'atr', 'date']
    df = df.dropna(subset=[c for c in critical_cols if c in df.columns]).reset_index(drop=True)
    return df
