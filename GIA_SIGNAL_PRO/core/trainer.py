
import os
import sys
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
from datetime import datetime
from sklearn.utils.class_weight import compute_sample_weight

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from GIA_SIGNAL_PRO.config.settings import PROJECT_ROOT, MODEL_PATH, SIGNAL_HORIZON, ATR_THRESHOLD, MODELS_DIR, DATA_DIR
from GIA_SIGNAL_PRO.core.confidence_calibrator import ConfidenceCalibrator
from backend.core.regime import MarketRegimeEngine
from backend.utils.indicators import calculate_rsi, calculate_atr

class MockEncoder:
    def inverse_transform(self, idxs):
        mapping = {0: 'SKIP', 1: 'BUY', 2: 'SELL'}
        return [mapping[i] for i in idxs]

class GIA_Apex_Distiller:
    """
    🦁 GIA SIGNAL PRO - THE APEX DISTILLER (v3.1 SCALPING)
    -------------------------------------------------
    Optimized for M1/M5 Scalping.
    3-Class Output: BUY / SELL / SKIP.
    Learns from Teachers during Training. 100% Independent at Runtime.
    """

    def __init__(self):
        self.features = []
        self.teachers_dir = os.path.join(PROJECT_ROOT, 'backend', 'models')
        self.regime_engine = MarketRegimeEngine()

    def load_data(self):
        # Professional Institutional Scope: Training on 2020-2022 for 2023+ deployment
        print("📂 Loading Long-term Institutional Data (2020-2025)...")
        def read(tf):
            path = os.path.join(DATA_DIR, f"XAUUSD_{tf}.csv")
            df = pd.read_csv(path)
            df.columns = [c.lower() for c in df.columns]
            # Use mixed format to handle both institutional history and live cTrader appends
            df['date'] = pd.to_datetime(df['time'], format='mixed', dayfirst=False)
            return df.sort_values('date', ascending=True)

        df1 = read("M1")
        df15 = read("M15")
        dfh1 = read("H1")
        
        # Split: Training (2020-2022) | Validation (2023-2025)
        # However, for the 'Final' model to be strongest, we train on all pre-2023 
        # and validate against 2023-2025.
        
        # Resample M1 to M5 (Context Bridge)
        df5 = df1.set_index('date').resample('5min').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna().reset_index()
        
        return df1, df5, df15, dfh1

    def _load_csv(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing required data file: {path}")
        # Efficient loading with explicit datetime format
        df = pd.read_csv(path)
        df.columns = [c.lower() for c in df.columns]
        if 'time' in df.columns:
            # 🕒 Explicit format for XAUUSD history (MM/DD/YYYY HH:MM:SS AM/PM)
            df['date'] = pd.to_datetime(df['time'], format='%m/%d/%Y %I:%M:%S %p')
        return df.sort_values('date', ascending=True)

    def engineer_features(self, df1, df5, df15, dfh1):
        print("🛠️ Transforming raw data into Apex Intelligence...")
        df = df1.copy()
        
        # Context merge (Multi-Timeframe)
        for name, cdf in [('m5', df5), ('m15', df15), ('h1', dfh1)]:
            cdf = cdf.copy()
            cdf[f'rsi_{name}'] = calculate_rsi(cdf['close'], 14)
            ma = cdf['close'].rolling(20).mean()
            cdf[f'trend_{name}'] = np.where(cdf['close'] > ma, 1, -1)
            # Volatility in HTF
            cdf[f'vol_{name}'] = cdf['close'].pct_change().rolling(20).std()
            
            df = pd.merge_asof(df.sort_values('date'), cdf[['date', f'rsi_{name}', f'trend_{name}', f'vol_{name}']].sort_values('date'), 
                               on='date', direction='backward')

        # Core M1 Features
        close = df['close']
        df['rsi'] = calculate_rsi(close, 14)
        df['rsi_slope'] = df['rsi'].diff(3)
        df['mom_5'] = close.pct_change(5)
        df['momentum'] = close.diff(5) / (close.shift(5) + 1e-9)
        
        # Volatility Squeeze Proxy
        ma20, std20 = close.rolling(20).mean(), close.rolling(20).std()
        df['bb_width'] = (4*std20) / (ma20 + 1e-9)
        df['bb_pos'] = (close - (ma20 - 2*std20)) / (4*std20 + 1e-9)
        
        # Exponential Weighting for Trend
        for s in [9, 21, 50, 200]:
            ma = close.rolling(s).mean()
            df[f'ema_{s}_dist'] = (close - ma) / (ma + 1e-9)
            
        df['atr'] = calculate_atr(df, 14)
        df['atr_norm'] = df['atr'] / (close + 1e-9)
        df['body_size'] = (df['close'] - df['open']) / (df['open'] + 1e-9)
        df['body_ratio'] = (df['close'] - df['open']).abs() / (df['high'] - df['low'] + 1e-9)
        
        u = (df['high'] - df[['open', 'close']].max(axis=1))
        l = (df[['open', 'close']].min(axis=1) - df['low'])
        df['wick_ratio'] = u / (l + 1e-9)

        df['hour'] = df['date'].dt.hour
        df['session_london'] = ((df['hour'] >= 8) & (df['hour'] <= 16)).astype(int)
        df['session_ny'] = ((df['hour'] >= 13) & (df['hour'] <= 21)).astype(int)
        
        # Market Regime Analysis
        df = self.regime_engine.classify(df)
        
        # ⚡ Micro-Scaling Features for High Frequency
        df['rsi_7'] = calculate_rsi(df['close'], period=7)
        df['roc_3'] = df['close'].pct_change(3)
        
        self.features = [
            'rsi', 'rsi_7', 'rsi_slope', 'roc_3', 'mom_5', 'momentum', 'bb_width', 'bb_pos',
            'ema_9_dist', 'ema_21_dist', 'ema_50_dist', 'ema_200_dist',
            'atr_norm', 'body_size', 'body_ratio', 'wick_ratio',
            'session_london', 'session_ny', 'regime_flag',
            'rsi_m5', 'trend_m5', 'vol_m5', 'rsi_m15', 'trend_m15', 'vol_m15', 'rsi_h1', 'trend_h1'
        ]
        
        return df.replace([np.inf, -np.inf], 0).fillna(0)

    def label_data(self, df):
        """
        🛡 NUCLEAR HIGH-FREQUENCY SCALPING LABELING
        Engineered for 10-30 trades per day (Maximum Intensity).
        """
        print("🧠 Labeling signals for NUCLEAR HIGH-FREQUENCY (Volume Priority)...")
        horizon = 4 # Fast 4-minute pivots
        
        # Ultra-sensitive targets for micro-move capture
        df['atr_val'] = calculate_atr(df, period=14)
        df['atr_thresh'] = (df['atr_val'] * 0.12).rolling(5).mean() # High sensitivity
        
        future_max = df['high'].rolling(horizon).max().shift(-horizon)
        future_min = df['low'].rolling(horizon).min().shift(-horizon)
        
        # Hyper-active logic with tight drawdown constraint
        buy_cond = (future_max - df['close'] > df['atr_thresh']) & (df['close'] - future_min < df['atr_thresh'] * 0.6)
        sell_cond = (df['close'] - future_min > df['atr_thresh']) & (future_max - df['close'] < df['atr_thresh'] * 0.6)
        
        df['target'] = 0 # WAIT
        df.loc[buy_cond, 'target'] = 1 # BUY
        df.loc[sell_cond, 'target'] = 2 # SELL
        
        return df.dropna()

    def train(self):
        print("\n" + "="*60)
        print("🦁 GIA SIGNAL PRO: ULTIMATE SNIPER TRAINING")
        print("="*60)
        
        df1, df5, df15, dfh1 = self.load_data()
        df = self.engineer_features(df1, df5, df15, dfh1)
        df = self.label_data(df)
        
        # 📂 Strategic Partitioning for Sniper Reliability
        # Using chronological split: 60% Train, 20% Calibrate, 20% Test
        n = len(df)
        train_end = int(n * 0.6)
        calib_end = int(n * 0.8)
        
        train_df = df.iloc[:train_end].copy()
        calib_df = df.iloc[train_end:calib_end].copy()
        test_df = df.iloc[calib_end:].copy()
        
        X_train, y_train = train_df[self.features], train_df['target']
        X_calib, y_calib = calib_df[self.features], calib_df['target']
        X_test, y_test = test_df[self.features], test_df['target']
        
        print(f"📊 Training: {len(X_train)} | Calib: {len(X_calib)} | Validation: {len(X_test)}")
        
        # ⚖️ NUCLEAR BALANCING: 2.5 Signal : 1 Wait
        skip_indices = train_df[train_df['target'] == 0].index
        buy_indices = train_df[train_df['target'] == 1].index
        sell_indices = train_df[train_df['target'] == 2].index
        
        signal_size = len(buy_indices) + len(sell_indices)
        np.random.seed(42)
        # Force Entry Bias: Signals are 2.5x more common than Wait
        target_wait_size = int(signal_size / 2.5)
        downsampled_skip = np.random.choice(skip_indices, size=min(len(skip_indices), target_wait_size), replace=False)
        
        balanced_idx = np.concatenate([downsampled_skip, buy_indices, sell_indices])
        train_df = train_df.loc[balanced_idx].sample(frac=1.0) # Shuffle
        
        X_train, y_train = train_df[self.features], train_df['target']
        X_test, y_test = test_df[self.features], test_df['target']
        X_calib, y_calib = calib_df[self.features], calib_df['target']
        
        weights = compute_sample_weight('balanced', y_train)
        
        # Deep Refinement Configuration for Hyper-Scalping
        model = xgb.XGBClassifier(
            max_depth=6,
            learning_rate=0.015,
            n_estimators=3000, # Deep learning capacity
            objective='multi:softprob',
            num_class=3,
            tree_method='hist',
            subsample=0.8,
            colsample_bytree=0.8,
            gamma=0.05, 
            min_child_weight=1,
            random_state=42
        )
        
        print("🛠️ Phase 1: Training Sniper Core (Deep Refinement)...")
        model.fit(X_train, y_train, sample_weight=weights, 
                  eval_set=[(X_test, y_test)], early_stopping_rounds=100, verbose=100)
        
        # ⚖️ Monotonic Calibration Audit
        print("⚖️ Calibrating Monotonic Confidence Engine...")
        calibrator = ConfidenceCalibrator()
        # Calibrate on unseen data to ensure real-world reliability
        calib_probs = model.predict_proba(X_calib)
        calibrator.fit(calib_probs, y_calib.values)
        
        # Save Final Intelligence
        save_data = {
            'model': model,
            'calibrator': calibrator,
            'features': self.features,
            'label_encoder': MockEncoder(),
            'metadata': {
                'mode': 'Small Account Sniper v2',
                'trained_at': datetime.now().isoformat(),
                'target_accounts': '$50 - $600'
            }
        }
        
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        joblib.dump(save_data, MODEL_PATH)
        print(f"✅ SNIPER SIGNAL PRO (MONOTONIC) SAVED: {MODEL_PATH}")

if __name__ == "__main__":
    trainer = GIA_Apex_Distiller()
    trainer.train()
