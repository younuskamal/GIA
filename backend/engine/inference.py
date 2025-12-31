"""
GIA Inference Engine - Stable Decision Unit
"""
import pandas as pd
import numpy as np
import os
import sys
import joblib
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path

# Fix path
BASE_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_BACKEND not in sys.path:
    sys.path.append(BASE_BACKEND)

from core.registry import ModelManager
from core.db import get_price_range, get_latest_price
from utils.indicators import (
    calculate_rsi, calculate_ema, calculate_atr,
    calculate_macd, calculate_bollinger_bands, calculate_stochastic
)

from backend.core.rules import SystemMode, SignalType
from backend.engine.strategy import StrategyHandler
from backend.core.regime import MarketRegimeEngine
from backend.data.processor import process_raw_data

class MockEncoder:
    def inverse_transform(self, idxs):
        mapping = {0: 'WAIT', 1: 'BUY', 2: 'SELL'}
        return [mapping[i] for i in idxs]

class GoldAnalysisModel:
    def __init__(self, model_path: str = None):
        self.manager = ModelManager()
        self.model_data = None
        self.model_loaded = False
        self.model_path = model_path or os.path.join(BASE_BACKEND, 'models', 'GIA_v14_PRO.pkl')
        self._load_active_model()
        # Initialize Strategy in Advisor Mode (Conservative)
        self.strategy = StrategyHandler(mode=SystemMode.ADVISOR_MODE)
        
    def _load_active_model(self):
        if os.path.exists(self.model_path):
            try:
                self.model_data = joblib.load(self.model_path)
                self.model_loaded = True
                print(f"🧠 AI ENGINE ACTIVE: {os.path.basename(self.model_path)}")
            except Exception as e:
                raise RuntimeError(f"CRITICAL: Failed to load {self.model_path}: {e}")
        else:
            raise FileNotFoundError(f"CRITICAL: AI Model missing at {self.model_path}")

    def get_features(self, interval='15m') -> Optional[pd.DataFrame]:
        """Calculates all professional features for live inference, supporting V2/MTF."""
        from backend.data.loaders import fetch_real_gold_data
        
        # 1. Fetch MTF Data
        raw_m15 = fetch_real_gold_data(interval='15m')
        raw_m30 = fetch_real_gold_data(interval='30m')
        raw_h1 = fetch_real_gold_data(interval='1h')
        
        if any(r is None or len(r) < 200 for r in [raw_m15, raw_m30, raw_h1]):
            return None

        # 2. Process Base Logic
        df_m15 = process_raw_data(raw_m15)
        df_m15['mom_10'] = df_m15['close'].pct_change(10)
        
        # 3. MTF Engineering (Side TFs)
        def engineer_mtf(df, suffix):
            df = df.copy()
            processed = process_raw_data(df)
            df[f'rsi_{suffix}'] = processed['rsi']
            e12, e26 = df['close'].ewm(span=12).mean(), df['close'].ewm(span=26).mean()
            df[f'macd_{suffix}'] = (e12 - e26) / (df['close'] + 1e-6)
            df[f'bb_width_{suffix}'] = (4 * df['close'].rolling(20).std()) / (df['close'].rolling(20).mean() + 1e-6)
            
            if suffix == 'h1':
                ema200 = df['close'].rolling(200).mean()
                df['ema_200_dist_h1'] = (df['close'] - ema200) / (df['close'] + 1e-6)
                df['mom_h1'] = df['close'].diff(4) / (df['close'] + 1e-6)
                df['trend_h1'] = np.where(df['close'] > ema200, 1, -1)
                df['rsi_h1'] = processed['rsi']
            return df[['date'] + [c for c in df.columns if c.endswith(suffix)]]

        df_m30 = engineer_mtf(raw_m30, 'm30')
        df_h1 = engineer_mtf(raw_h1, 'h1')

        # 4. Merge & Full V2 Engineering
        df = pd.merge_asof(df_m15.sort_values('date'), df_m30.sort_values('date'), on='date', direction='backward')
        df = pd.merge_asof(df, df_h1.sort_values('date'), on='date', direction='backward')

        # Regime & V2 Specifics
        df = MarketRegimeEngine().classify(df)
        
        close = df['close']
        df['atr_norm'] = df['atr'] / (close + 1e-6)
        # vol_ratio: dynamic volatility stretch
        avg_atr = df['atr_norm'].rolling(100).mean()
        df['vol_ratio'] = df['atr_norm'] / (avg_atr + 1e-6)
        df['vol_regime'] = np.where(df['vol_ratio'] > 1.2, 1, 0)
        
        df['is_peak_hour'] = ((df['date'].dt.hour >= 7) & (df['date'].dt.hour <= 22)).astype(int)
        
        ma20 = df['close'].rolling(20).mean()
        df['price_dist_bb'] = (df['close'] - ma20) / (ma20 + 1e-6)
        
        # Stability
        df = df.replace([np.inf, -np.inf], 0).fillna(0)
        
        return df.tail(10)

    def analyze_market(self, df: pd.DataFrame) -> Dict:
        """
        Analyzes the provided dataframe (assumes features are present).
        Used by Auto-Trader and Backtesters.
        """
        if not self.model_loaded:
             return self._rule_based_analysis()

        # Extract Features for Last Row
        m_type = self.model_data.get('model_type', 'XGBOOST')
        feature_cols = self.model_data['feature_columns']
        
        # Check if columns exist
        missing = [c for c in feature_cols if c not in df.columns]
        if missing:
            return {"success": False, "error": f"Missing features: {missing}"}

        if m_type == 'XGBOOST':
            X = df.tail(1)[feature_cols]
            probs = self.model_data['model'].predict_proba(X)[0]
        else: # LSTM
            import tensorflow as tf
            # ... (LSTM Logic omitted for brevity as v14 is XGB) ...
            # If needed, we'd replicate the scaling/sequence logic here.
            # Allowing XGB only for v14 stability.
            return {"success": False, "error": "LSTM Live predict not implemented in analyze_market"}
            
        pred_idx = int(np.argmax(probs))
        confidence = float(np.max(probs))
        
        raw_decision = self.model_data['label_encoder'].inverse_transform([pred_idx])[0]
        
        return {
            "signal": raw_decision,
            "confidence": confidence,
            "risk_level": "UNKNOWN", # Calculated by StrategyHandler externally
            "explanation": "Raw Model Inference"
        }

    def analyze(self) -> Dict:
        """Unified analysis unit that mirrors the Backtest decision pipeline."""
        from backend.data.loaders import fetch_real_gold_data
        from backend.data.processor import process_raw_data
        
        # 1. Fetch Raw M15 Data
        raw_df = fetch_real_gold_data(interval='15m')
        if raw_df is None or len(raw_df) < 500: 
            return {"success": False, "error": "Insufficient history for M15 Analysis"}
            
        # 2. Process Features (Backtest standard)
        df_processed = process_raw_data(raw_df)
        if df_processed is None or df_processed.empty: 
            return {"success": False, "error": "Feature Engineering Failed"}
        
        # 3. Model Inference
        feature_cols = self.model_data['feature_columns']
        latest = df_processed.tail(1)
        
        probs = self.model_data['model'].predict_proba(latest[feature_cols])[0]
        confidence = float(np.max(probs))
        pred_idx = int(np.argmax(probs))
        raw_signal = self.model_data['label_encoder'].inverse_transform([pred_idx])[0]
        
        # 4. Strategy Analysis Unit (ATR & Context)
        atr_val = df_processed['atr'].iloc[-1] if 'atr' in df_processed.columns else 0.0
        ctx = {"news_impact_score": df_processed['news_impact_score'].iloc[-1]}
        
        # Decision via StrategyHandler (Mirroring rules applied in backtest)
        decision_pkg = self.strategy.apply_strategy(raw_signal, confidence, ctx)
        
        return {
            "success": True,
            "signal": decision_pkg['signal'],
            "confidence": confidence,
            "raw_prediction": raw_signal,
            "atr": atr_val,
            "timestamp": df_processed['date'].iloc[-1],
            "explanation": decision_pkg['explanation']
        }
