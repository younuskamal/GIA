
import pandas as pd
import numpy as np
import os
import sys

# Ensure backend is in path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

def engineer_features_v1_1(df):
    """
    Advanced Feature Engineering for GIA v1.1 PRO.
    - Regime Detection
    - Time-of-day encoding
    - EMA Distances
    - Volatility Normalization
    """
    df = df.copy()
    # Normalize column names to lowercase for consistency
    df.columns = [c.lower() for c in df.columns]
    
    if 'time' in df.columns:
        df['date'] = pd.to_datetime(df['time'], format='%m/%d/%Y %I:%M:%S %p')
    else:
        # Fallback if time is index or named differently
        df['date'] = pd.to_datetime(df.index)

    # 1. Regime Engine
    from backend.core.regime import MarketRegimeEngine
    engine = MarketRegimeEngine()
    df = engine.classify(df)
    
    # 2. EMA Distances (EMA50, EMA200)
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['dist_ema50'] = (df['close'] - df['ema_50']) / df['ema_50']
    df['dist_ema200'] = (df['close'] - df['ema_200']) / df['ema_200']
    
    # 3. Time-of-day encoding (UTC based on common cTrader exports)
    df['hour'] = df['date'].dt.hour
    df['is_london'] = ((df['hour'] >= 8) & (df['hour'] <= 16)).astype(int)
    df['is_ny'] = ((df['hour'] >= 13) & (df['hour'] <= 21)).astype(int)
    
    # 4. Volatility Normalization
    df['atr_norm'] = df['atr'] / df['close']
    
    # 5. Traditional Indicators (Momentum & Wicks)
    df['ret_1'] = df['close'].pct_change(1)
    df['ret_5'] = df['close'].pct_change(5)
    df['body_size'] = (df['close'] - df['open']).abs() / df['close']
    df['upper_wick'] = (df['high'] - df[['open', 'close']].max(axis=1)) / df['close']
    df['lower_wick'] = (df[['open', 'close']].min(axis=1) - df['low']) / df['close']
    
    # 6. Advanced Momentum
    df['rsi_slope'] = df['rsi'].diff(3)
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = (exp1 - exp2) / df['close']
    df['stoch_k'] = (df['close'] - df['low'].rolling(14).min()) / (df['high'].rolling(14).max() - df['low'].rolling(14).min())
    
    # 7. Regime stability (Stability metric)
    df['regime_stability'] = df['regime_flag'].rolling(window=10).std()
    
    return df.dropna()

def create_labels(df, horizon=24, atr_multiplier=1.5):
    """
    Creates dynamic BUY (1), SELL (2), WAIT (0) labels based on ATR.
    Alinged with Backtest: 24-bar window (6 hours) for 1.5 * ATR move.
    """
    df = df.copy()
    
    # Dynamic target threshold based on ATR
    df['target_move'] = df['atr'] * atr_multiplier
    
    df['future_max_delta'] = df['close'].rolling(window=horizon).max().shift(-horizon) - df['close']
    df['future_min_delta'] = df['close'].rolling(window=horizon).min().shift(-horizon) - df['close']
    
    df['target'] = 0 # WAIT
    df.loc[df['future_max_delta'] > df['target_move'], 'target'] = 1 # BUY
    df.loc[df['future_min_delta'] < -df['target_move'], 'target'] = 2 # SELL
    
    return df.dropna()
