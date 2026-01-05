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

# Inject into __main__ to solve joblib/pickle deserialization issues
import __main__
__main__.MockEncoder = MockEncoder

class GoldAnalysisModel:
    def __init__(self, model_path: str = None):
        self.manager = ModelManager()
        self.model_data = None
        self.model_loaded = False
        self.model_path = model_path or os.path.join(BASE_BACKEND, 'models', 'GIA_v14_PRO.pkl')
        self.last_mtime = 0
        self._load_active_model()
        is_predator = "PREDATOR" in self.model_path.upper()
        # Initialize Strategy in Advisor Mode (Conservative)
        self.strategy = StrategyHandler(mode=SystemMode.ADVISOR_MODE, uhf_mode=is_predator)
        
    def _load_active_model(self):
        if os.path.exists(self.model_path):
            try:
                mtime = os.path.getmtime(self.model_path)
                if mtime > self.last_mtime:
                    self.model_data = joblib.load(self.model_path)
                    self.model_loaded = True
                    self.last_mtime = mtime
                    print(f"🧠 AI ENGINE {'LOADED' if self.last_mtime == mtime else 'RELOADED'}: {os.path.basename(self.model_path)}")
            except Exception as e:
                print(f"⚠️ Failed to load model: {e}")
        else:
            print(f"⚠️ AI Model missing at {self.model_path}")

    def analyze(self) -> Dict:
        """Runs the full analysis cycle with hot-reload support."""
        self._load_active_model() # Hot-reload if file changed
        if not self.model_loaded: return {"success": False, "error": "Model not loaded"}

    def get_features(self, interval='15m') -> Optional[pd.DataFrame]:
        """Calculates all professional features for live inference, supporting V2/MTF."""
        from backend.data.loaders import fetch_real_gold_data
        
        # 1. Fetch MTF Data
        raw_m15 = fetch_real_gold_data(interval='15m')
        raw_m30 = fetch_real_gold_data(interval='30m')
        raw_h1 = fetch_real_gold_data(interval='1h')
        
        if any(r is None or len(r) < 150 for r in [raw_m15, raw_m30, raw_h1]):
            return None

        # 2. Process Base Logic
        df_m15 = process_raw_data(raw_m15)
        
        # Side TFs Engineering
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

        # 3. Merge & Logic
        df = pd.merge_asof(df_m15.sort_values('date'), df_m30.sort_values('date'), on='date', direction='backward')
        df = pd.merge_asof(df, df_h1.sort_values('date'), on='date', direction='backward')
        df = MarketRegimeEngine().classify(df)
        
        # 4. Final V2 Engineering (Coordinated with Training)
        close = df['close']
        df['rsi_slope'] = df['rsi'].diff(3)
        df['mom_5'] = close.pct_change(5)
        df['mom_10'] = close.pct_change(10)
        df['vol_20'] = close.pct_change(1).rolling(20).std()
        
        e12, e26 = close.ewm(span=12).mean(), close.ewm(span=26).mean()
        df['macd_norm'] = (e12 - e26) / (close + 1e-6)
        
        ma20, std20 = close.rolling(20).mean(), close.rolling(20).std()
        df['bb_width'] = (4 * std20) / (ma20 + 1e-6)
        df['bb_pos'] = (close - (ma20 - 2*std20)) / (4*std20 + 1e-6)
        df['price_dist_bb'] = (close - ma20) / (ma20 + 1e-6)
        
        for s in [9, 21, 50, 200]:
            ma = close.rolling(s).mean()
            df[f'ema_{s}_dist'] = (close - ma) / (ma + 1e-6)
        df['ribbon_align'] = (np.sign(df['ema_21_dist']) + np.sign(df['ema_50_dist']) + np.sign(df.get('ema_200_dist', 0))) / 3.0
        
        df['vol_ratio'] = (df['vol_20'] / df['vol_20'].rolling(200).mean()).fillna(1.0)
        df['vol_regime'] = np.where(df['vol_ratio'] > 1.2, 1, 0)
        df['atr_norm'] = df['atr'] / (close + 1e-6)
        
        avg_body = (df['close'] - df['open']).abs().rolling(20).mean()
        df['body_rel'] = (df['close'] - df['open']).abs() / (avg_body + 1e-6)
        df['body_size'] = (df['close'] - df['open']) / (df['open'] + 1e-6)
        df['upper_wick'] = (df['high'] - df[['open', 'close']].max(axis=1)) / (close + 1e-6)
        df['lower_wick'] = (df[['open', 'close']].min(axis=1) - df['low']) / (close + 1e-6)
        df['wick_ratio'] = (df['upper_wick'] - df['lower_wick']) / (df['upper_wick'] + df['lower_wick'] + 1e-6)
        
        df['coiling'] = df['bb_width'] / (df['bb_width'].rolling(50).mean() + 1e-6)
        df['velocity'] = close.diff(5) / (std20 + 1e-6)
        
        # 🚀 Institutional High-Intelligence Features
        df['price_acceleration'] = df['velocity'].diff(3)
        df['liquidity_shock'] = df['volume'] / (df['volume'].rolling(50).mean() + 1e-9)
        
        diff_sum = close.diff().abs().rolling(10).sum()
        range_sum = (df['high'].rolling(10).max() - df['low'].rolling(10).min() + 1e-9)
        df['market_entropy'] = diff_sum / range_sum
        
        ma50 = close.rolling(50).mean()
        df['exhaustion_index'] = (close - ma50).abs() / (std20 * 2 + 1e-9)
        
        df['div_proxy'] = close.pct_change(5) - df['rsi'].pct_change(5)
        
        lo100 = close.rolling(100).min()
        hi100 = close.rolling(100).max()
        df['structure_strength'] = (close - lo100) / (hi100 - lo100 + 1e-9)

        df['hour'] = df['date'].dt.hour
        df['is_peak'] = ((df['hour'] >= 7) & (df['hour'] <= 22)).astype(int)
        df['is_peak_hour'] = df['is_peak']
        df['trend_harmony'] = (np.sign(df['macd_norm']) + np.sign(df.get('macd_m30', 0)) + np.sign(df.get('macd_h1', 0))) / 3.0


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
        # 1. Fetch & Engineer Full Features (MTF)
        df_full = self.get_features() # This already fetches M15, M30, H1 and engineers all features
        
        if df_full is None or df_full.empty:
            return {"success": False, "error": "Insufficient history or feature engineering failure"}
            
        # 2. Model Inference
        feature_cols = self.model_data['feature_columns']
        latest = df_full.tail(1)
        
        # Check mapping for features
        missing = [c for c in feature_cols if c not in latest.columns]
        if missing:
            print(f"   DEBUG: Feature Columns in Data: {list(latest.columns)}")
            return {"success": False, "error": f"Model requires features missing in latest data: {missing}"}

            
        probs = self.model_data['model'].predict_proba(latest[feature_cols])[0]
        confidence = float(np.max(probs))
        pred_idx = int(np.argmax(probs))
        
        # Multi-model encoder support
        encoder = self.model_data.get('label_encoder', self.model_data.get('encoder'))
        raw_signal = encoder.inverse_transform([pred_idx])[0]
        
        # 3. Strategy Analysis Unit (ATR & Context)
        atr_val = df_full['atr'].iloc[-1] if 'atr' in df_full.columns else 0.0
        # News impact is optional
        news_score = df_full['news_impact_score'].iloc[-1] if 'news_impact_score' in df_full.columns else 0
        ctx = {"news_impact_score": news_score}
        
        # Decision via StrategyHandler
        decision_pkg = self.strategy.apply_strategy(raw_signal, confidence, ctx)
        
        return {
            "success": True,
            "signal": decision_pkg['signal'],
            "confidence": confidence,
            "raw_prediction": raw_signal,
            "atr": atr_val,
            "timestamp": df_full['date'].iloc[-1],
            "explanation": decision_pkg['explanation']
        }
