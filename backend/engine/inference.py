"""
GIA Inference Engine - Stable Decision Unit
"""
import pandas as pd
import numpy as np
import logging
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

def engineer_mtf(df_raw, suffix):
    """Engineers features for secondary timeframes with appropriate suffix identification."""
    from backend.core.regime import MarketRegimeEngine
    df = df_raw.copy()
    # Ensure EMA 200 is present for structure
    close = df['close']
    ema200 = close.ewm(span=200, adjust=False).mean()
    
    # 🦁 Technical Indicators with suffix mapping
    df[f'rsi_{suffix}'] = calculate_rsi(close, 14)
    df[f'macd_{suffix}'] = (close.ewm(span=12).mean() - close.ewm(span=26).mean()) / (close + 1e-9)
    df[f'mom_{suffix}'] = close.pct_change(5)
    
    ma20, std20 = close.rolling(20).mean(), close.rolling(20).std()
    df[f'bb_width_{suffix}'] = (4 * std20) / (ma20 + 1e-9)
    df[f'ema_200_dist_{suffix}'] = (close - ema200) / (close + 1e-9)
    
    # 🕵️ Trend Awareness
    regime_df = MarketRegimeEngine().classify(df)
    df[f'trend_{suffix}'] = regime_df['regime_flag']
    
    # Clean-up and Keep subset
    df = df.replace([np.inf, -np.inf], 0).fillna(0)
    cols = ['date', f'rsi_{suffix}', f'macd_{suffix}', f'bb_width_{suffix}', f'ema_200_dist_{suffix}', f'mom_{suffix}', f'trend_{suffix}']
    return df[cols]

class EliteDuoEngine:
    """Institutional Master Engine that manages PRO (M15) and FLASH (M1) models in harmony."""
    def __init__(self, models_dir: str):
        self.pro = GoldAnalysisModel(os.path.join(models_dir, "GIA_v2_PRO.pkl"))
        self.flash = GoldAnalysisModel(os.path.join(models_dir, "GIA_v2_FLASH.pkl"))
        self.strategy = self.pro.strategy # Shared strategy handler context
        
    def analyze_pro(self):
        return self.pro.analyze()
        
    def analyze_flash(self):
        return self.flash.analyze()

class GoldAnalysisModel:
    def __init__(self, model_path: str = None):
        self.manager = ModelManager()
        self.model_data = None
        self.model_loaded = False
        self.model_path = model_path or os.path.join(BASE_BACKEND, 'models', 'GIA_v14_PRO.pkl')
        self.last_mtime = 0
        self._load_active_model()
        self.is_flash = "FLASH" in self.model_path.upper()
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
                    self.is_flash = "FLASH" in self.model_path.upper()
                    print(f"🧠 AI ENGINE {'LOADED' if self.last_mtime == mtime else 'RELOADED'}: {os.path.basename(self.model_path)}")
            except Exception as e:
                print(f"⚠️ Failed to load model: {e}")
        else:
            print(f"⚠️ AI Model missing at {self.model_path}")

    def analyze(self, record_trade: bool = True) -> Dict:
        """Unified analysis unit that mirrors the Backtest decision pipeline."""
        self._load_active_model() 
        if not self.model_loaded: return {"success": False, "error": "Model not loaded"}

        # 1. Fetch & Engineer Full Features (MTF)
        df_full = self.get_features() 
        
        if df_full is None or df_full.empty:
            print(f"⚠️ Analysis failed: get_features returned None or empty.")
            return {"success": False, "error": "Insufficient history or feature engineering failure"}
            
        # 2. Model Inference
        feature_cols = self.model_data['feature_columns']
        latest = df_full.tail(1)
        
        missing = [c for c in feature_cols if c not in latest.columns]
        if missing:
            return {"success": False, "error": f"Model requires features missing in latest data: {missing}"}

        probs = self.model_data['model'].predict_proba(latest[feature_cols])[0]
        confidence = float(np.max(probs))
        pred_idx = int(np.argmax(probs))
        
        # Multi-model encoder support
        encoder = self.model_data.get('label_encoder', self.model_data.get('encoder'))
        raw_signal = encoder.inverse_transform([pred_idx])[0]
        
        # 3. Strategy Analysis Unit (ATR & Context)
        atr_val = df_full['atr'].iloc[-1] if 'atr' in df_full.columns else 0.0
        regime_flag = int(df_full['regime_flag'].iloc[-1]) if 'regime_flag' in df_full.columns else 0
        
        ctx = {
            "news_impact_score": 0, # Placeholder
            "date": df_full['date'].iloc[-1],
            "regime_flag": regime_flag,
            "market_entropy": float(df_full['market_entropy'].iloc[-1]),
            "exhaustion_index": float(df_full['exhaustion_index'].iloc[-1]),
            "atr": float(atr_val),
            "spread": float(df_full['bb_width'].iloc[-1])
        }
        
        # Decision via StrategyHandler
        decision_pkg = self.strategy.apply_strategy(raw_signal, confidence, ctx, record_trade=record_trade)
        
        # 🦁 LOGGING IQ: Log the transition from AI Raw -> Strategy Filter
        log_msg = f"🧠 AI RAW: {raw_signal} (Conf: {confidence:.2f}) -> GIA FILTER: {decision_pkg['signal']} | Reason: {decision_pkg['explanation']}"
        logging.info(log_msg)
        print(f"   {log_msg}")

        return {
            "success": True,
            "signal": decision_pkg['signal'],
            "confidence": confidence,
            "raw_prediction": raw_signal,
            "price": float(latest['close'].iloc[-1]),
            "atr": float(atr_val),
            "rsi": float(latest['rsi'].iloc[-1]) if 'rsi' in latest.columns else 50.0,
            "vol_regime": float(latest['vol_regime'].iloc[-1]) if 'vol_regime' in latest.columns else 1.0,
            "news_safe": True, # Link to News Guard in future
            "regime_flag": regime_flag,
            "market_entropy": ctx["market_entropy"],
            "exhaustion_index": ctx["exhaustion_index"],
            "timestamp": df_full['date'].iloc[-1],
            "explanation": decision_pkg['explanation']
        }

    def get_features(self, interval='15m') -> Optional[pd.DataFrame]:
        """Calculates all professional features for live inference, supporting V2/MTF."""
        from backend.data.loaders import fetch_real_gold_data
        
        # 1. Fetch MTF Data
        if self.is_flash:
            # ⚡ FLASH MODE: M1 Base, plus M15/H1 context
            raw_base = fetch_real_gold_data(interval='1m')
            raw_m15 = fetch_real_gold_data(interval='15m')
            raw_h1 = fetch_real_gold_data(interval='1h')
            
            if any(r is None or len(r) < 100 for r in [raw_base, raw_m15, raw_h1]):
                return None
                
            df_base = process_raw_data(raw_base)
            df_m15 = engineer_mtf(raw_m15, 'm15')
            df_h1 = engineer_mtf(raw_h1, 'h1')
            
            print(f"   📊 DEBUG: Base: {len(df_base)}, M15: {len(df_m15)}, H1: {len(df_h1)}") # DEBUG
            
            df = pd.merge_asof(df_base.sort_values('date'), df_m15.sort_values('date'), on='date', direction='backward')
            df = pd.merge_asof(df, df_h1.sort_values('date'), on='date', direction='backward')
            
            print(f"   📊 DEBUG: Merged Size: {len(df)}") # DEBUG
        else:
            raw_base = fetch_real_gold_data(interval='15m')
            raw_m30 = fetch_real_gold_data(interval='30m')
            raw_h1 = fetch_real_gold_data(interval='1h')
            
            if any(r is None or len(r) < 100 for r in [raw_base, raw_m30, raw_h1]):
                print(f"⚠️ Data Insufficient: Base={len(raw_base) if raw_base is not None else 'N/A'}, M30={len(raw_m30) if raw_m30 is not None else 'N/A'}, H1={len(raw_h1) if raw_h1 is not None else 'N/A'}")
                return None
                
            df_base = process_raw_data(raw_base)
            df_m30 = engineer_mtf(raw_m30, 'm30')
            df_h1 = engineer_mtf(raw_h1, 'h1')
            
            df = pd.merge_asof(df_base.sort_values('date'), df_m30.sort_values('date'), on='date', direction='backward')
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
        
        for s in [9, 21, 50, 100, 200]:
            ma = close.ewm(span=s, adjust=False).mean()
            df[f'ema_{s}_dist'] = (close - ma) / (ma + 1e-9)
            
        df['ribbon_align'] = (np.sign(df['ema_9_dist']) + np.sign(df['ema_21_dist']) + np.sign(df['ema_50_dist']) + np.sign(df.get('ema_100_dist', 0)) + np.sign(df['ema_200_dist'])) / 5.0
        
        df['vol_ratio'] = std20 / (std20.rolling(50).mean() + 1e-9)
        df['vol_regime'] = (std20 / (std20.rolling(200).mean() + 1e-9)).fillna(1.0)
        df['atr_norm'] = df['atr'] / (close + 1e-9)
        
        df['body_rel'] = (close - df['open']).abs() / (df['high'] - df['low'] + 1e-9)
        df['upper_wick'] = (df['high'] - df[['open', 'close']].max(axis=1)) / (close + 1e-9)
        df['lower_wick'] = (df[['open', 'close']].min(axis=1) - df['low']) / (close + 1e-9)
        df['wick_ratio'] = df['upper_wick'] / (df['lower_wick'] + 1e-9)
        
        df['coiling'] = df['bb_width'] / (df['bb_width'].rolling(50).mean() + 1e-9)
        df['velocity'] = close.diff(5) / (std20 + 1e-9)
        
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

        # Session Awareness (UTC sync)
        hour = df['date'].dt.hour
        df['is_london'] = ((hour >= 8) & (hour <= 16)).astype(int)
        df['is_newyork'] = ((hour >= 13) & (hour <= 21)).astype(int)
        df['session_active'] = ((df['is_london'] == 1) | (df['is_newyork'] == 1)).astype(int)
        df['is_peak'] = ((hour >= 7) & (hour <= 22)).astype(int)

        df['trend_harmony'] = (
            np.sign(df['macd_norm']) + 
            np.sign(df.get('macd_m15', df.get('macd_m30', 0))) + 
            np.sign(df.get('macd_h1', 0))
        ) / 3.0
        
        # Map Regime for Model
        df['regime_flag'] = df['regime'].map({'TRENDING': 1, 'RANGING': 0, 'VOLATILE': 2, 'STALL': -1}).fillna(0)


        df = df.replace([np.inf, -np.inf], 0).fillna(0)
        print(f"   📊 FEATURE ENGINEERING: Result Size {len(df)} rows | Columns: {len(df.columns)}")
        return df.tail(10)
