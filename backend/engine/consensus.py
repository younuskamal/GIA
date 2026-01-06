
import pandas as pd
import numpy as np
import os
import joblib
from typing import Dict
from backend.engine.strategy import StrategyHandler
from backend.core.rules import SystemMode
from backend.data.loaders import fetch_real_gold_data
from backend.data.processor import process_raw_data
from backend.core.regime import MarketRegimeEngine

class MockEncoder:
    def inverse_transform(self, idxs):
        mapping = {0: 'WAIT', 1: 'BUY', 2: 'SELL'}
        return [mapping[i] for i in idxs]

class TripleConsensusModel:
    def __init__(self, models_dir: str):
        self.models_dir = models_dir
        self.models = {}
        self.strategy = StrategyHandler(mode=SystemMode.ADVISOR_MODE)
        self._load_models()

    def _load_models(self):
        model_names = {
            'risk': 'GIA_v14_PRO.pkl',
            'core': 'GIA_v2_PRO.pkl',
            'flash': 'GIA_v2_FLASH.pkl'
        }
        for key, name in model_names.items():
            path = os.path.join(self.models_dir, name)
            if os.path.exists(path):
                self.models[key] = joblib.load(path)
                print(f"✅ Loaded Consensus Component: {name}")
            else:
                print(f"⚠️ Warning: Consensus model {name} missing at {path}")

    def _engineer_full_features(self, df_m15, df_m30, df_h1):
        """Standardized Feature Engineering: Matches v2_PRO Training & Backtest."""
        df = df_m15.copy()
        
        # 1. Merge MTF Data
        df = pd.merge_asof(df.sort_values('date'), df_m30.sort_values('date'), on='date', direction='backward')
        df = pd.merge_asof(df, df_h1.sort_values('date'), on='date', direction='backward')

        # 2. Market Regime
        df = MarketRegimeEngine().classify(df)

        # 3. Base Indicators Fixes
        close = df['close']
        df['rsi_slope'] = df['rsi'].diff(3)
        df['mom_5'] = close.pct_change(5)
        df['mom_10'] = close.pct_change(10)
        df['vol_20'] = close.pct_change(1).rolling(20).std()
        
        # MACD Norm (M15)
        e12, e26 = close.ewm(span=12).mean(), close.ewm(span=26).mean()
        df['macd_norm'] = (e12 - e26) / (close + 1e-6)

        # Bollinger Bounds
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        df['bb_width'] = (4 * std20) / (ma20 + 1e-6)
        df['bb_pos'] = (close - (ma20 - 2*std20)) / (4*std20 + 1e-6)
        df['price_dist_bb'] = (close - ma20) / (ma20 + 1e-6)

        # 4. V2 Advanced Features
        # Ribbon & Distances
        for s in [9, 21, 50, 200]:
            ma = close.rolling(s).mean()
            df[f'ema_{s}_dist'] = (close - ma) / (ma + 1e-6)
        df['ribbon_align'] = (np.sign(df['ema_21_dist']) + np.sign(df['ema_50_dist']) + np.sign(df.get('ema_200_dist', 0))) / 3.0
        
        # Dynamics
        bw = df['bb_width']
        df['coiling'] = bw / (bw.rolling(50).mean() + 1e-6)
        df['velocity'] = close.diff(5) / (std20 + 1e-6)
        
        # 🚀 Institutional High-Intelligence
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

        # Temporal & Harmony
        df['hour'] = df['date'].dt.hour
        df['is_peak'] = ((df['hour'] >= 7) & (df['hour'] <= 22)).astype(int)
        df['is_peak_hour'] = df['is_peak']
        df['trend_harmony'] = (np.sign(df['macd_norm']) + np.sign(df.get('macd_m30', 0)) + np.sign(df.get('macd_h1', 0))) / 3.0

        
        # Final Guard
        df = df.replace([np.inf, -np.inf], 0).fillna(0)
        return df

    def _engineer_mtf_side(self, df, suffix):
        """Prepare side timeframe data with necessary suffixes."""
        df = df.copy()
        df[f'rsi_{suffix}'] = process_raw_data(df)['rsi'] # Use processor for base
        e12 = df['close'].ewm(span=12).mean()
        e26 = df['close'].ewm(span=26).mean()
        df[f'macd_{suffix}'] = (e12 - e26) / (df['close'] + 1e-6)
        std = df['close'].rolling(20).std()
        ma = df['close'].rolling(20).mean()
        df[f'bb_width_{suffix}'] = (4 * std) / (ma + 1e-6)
        
        if suffix == 'h1':
            ema200 = df['close'].rolling(200).mean()
            df['ema_200_dist_h1'] = (df['close'] - ema200) / (df['close'] + 1e-6)
            df['mom_h1'] = df['close'].diff(4) / (df['close'] + 1e-6)
            df['trend_h1'] = np.where(df['close'] > ema200, 1, -1)
            
        cols = ['date'] + [c for c in df.columns if c.endswith(suffix)]
        return df[cols]

    def analyze(self) -> Dict:
        if len(self.models) < 3:
            return {"success": False, "error": "Consensus requires all 3 models (v14, v2_pro, v2_flash)"}

        # 1. Fetch Data (All Timeframes)
        raw_m15 = fetch_real_gold_data(interval='15m')
        raw_m30 = fetch_real_gold_data(interval='30m')
        raw_h1 = fetch_real_gold_data(interval='1h')
        
        if any(r is None or len(r) < 200 for r in [raw_m15, raw_m30, raw_h1]):
            return {"success": False, "error": f"Insufficient history (200 bars required). Found M15:{len(raw_m15) if raw_m15 is not None else 0}, M30:{len(raw_m30) if raw_m30 is not None else 0}, H1:{len(raw_h1) if raw_h1 is not None else 0}"}

        # 2. Process Base Logic
        df_m15 = process_raw_data(raw_m15)
        df_m30 = self._engineer_mtf_side(raw_m30, 'm30')
        df_h1 = self._engineer_mtf_side(raw_h1, 'h1')
        
        # 3. Full Engineering Sync
        df = self._engineer_full_features(df_m15, df_m30, df_h1)
        latest = df.tail(1)
        regime_flag = int(latest['regime_flag'].iloc[-1]) if 'regime_flag' in latest.columns else 0

        # 4. Get Signals from all 3
        # v14 (Risk Governor)
        m14 = self.models['risk']
        try:
            p14 = m14['model'].predict(latest[m14['feature_columns']])[0]
        except KeyError as e:
            print(f"   DEBUG [Consensus/Risk]: Missing {e} in {list(latest.columns)}")
            return {"success": False, "error": f"Consensus Risk model missing features: {e}"}

        # p14: 0=WAIT, 1=BUY, 2=SELL
        
        # v2 PRO (Core)
        m2p = self.models['core']
        try:
            pr2p = m2p['model'].predict_proba(latest[m2p['feature_columns']])[0]
        except KeyError as e:
            print(f"   DEBUG [Consensus/Core]: Missing {e} in {list(latest.columns)}")
            return {"success": False, "error": f"Consensus Core model missing features: {e}"}
        s2p = m2p['label_encoder'].inverse_transform([np.argmax(pr2p)])[0]

        c2p = np.max(pr2p)
        
        # v2 FLASH (Tactical)
        m2f = self.models['flash']
        pr2f = m2f['model'].predict_proba(latest[m2f['feature_columns']])[0]
        s2f = m2f['label_encoder'].inverse_transform([np.argmax(pr2f)])[0]
        c2f = np.max(pr2f)

        # 5. Consensus Logic
        final_sig = 'WAIT'
        final_conf = 0.0
        sizing = 1.0
        explanation = "Agreement not met"

        v14_allows_buy = (p14 == 1)
        v14_allows_sell = (p14 == 2)

        if s2p == 'BUY' and v14_allows_buy:
            if s2f == 'BUY':
                if (c2p + c2f)/2.0 >= 0.6:
                    final_sig, final_conf, sizing = 'BUY', (c2p + c2f)/2.0, 1.0
                    explanation = "TRIPLE CONSENSUS: Full Agreement"
            elif s2f == 'WAIT':
                if c2p >= 0.65:
                    final_sig, final_conf, sizing = 'BUY', c2p, 0.5
                    explanation = "ASSISTED ENTRY: Core Buy + Flash Wait"
        
        elif s2p == 'SELL' and v14_allows_sell:
            if s2f == 'SELL':
                if (c2p + c2f)/2.0 >= 0.6:
                    final_sig, final_conf, sizing = 'SELL', (c2p + c2f)/2.0, 1.0
                    explanation = "TRIPLE CONSENSUS: Full Agreement"
            elif s2f == 'WAIT':
                if c2p >= 0.65:
                    final_sig, final_conf, sizing = 'SELL', c2p, 0.5
                    explanation = "ASSISTED ENTRY: Core Sell + Flash Wait"

        if p14 == 0 and final_sig != 'WAIT':
             explanation += " (Risk Veto Softened - Force Wait Recommended)"
             final_sig = 'WAIT'

        return {
            "success": True,
            "signal": final_sig,
            "confidence": final_conf,
            "sizing_multiplier": sizing,
            "atr": df['atr'].iloc[-1],
            "regime_flag": regime_flag,
            "market_entropy": float(latest['market_entropy'].iloc[-1]) if 'market_entropy' in latest.columns else 0.5,
            "exhaustion_index": float(latest['exhaustion_index'].iloc[-1]) if 'exhaustion_index' in latest.columns else 0.0,
            "explanation": explanation,
            "brains": {
                "risk": "BUY" if p14==1 else "SELL" if p14==2 else "WAIT",
                "core": f"{s2p} ({round(c2p*100)}%)",
                "flash": f"{s2f} ({round(c2f*100)}%)"
            }
        }
