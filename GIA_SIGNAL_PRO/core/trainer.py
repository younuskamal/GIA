
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
        # 🛡️ ADAPTIVE INSTITUTIONAL MODE: Detect available range automatically
        print("📂 Loading Institutional Data (v1.0.1 Adaptive)...")
        def read(tf):
            path = os.path.join(DATA_DIR, f"XAUUSD_{tf}.csv")
            df = pd.read_csv(path)
            df.columns = [c.lower() for c in df.columns]
            df['date'] = pd.to_datetime(df['time'], format='mixed', dayfirst=False)
            return df.sort_values('date', ascending=True)

        df1 = read("M1")
        df15 = read("M15")
        dfh1 = read("H1")
        
        # Resample M1 to M5 (Context Bridge)
        df5 = df1.set_index('date').resample('5min').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna().reset_index()
        
        # 📋 ADAPTIVE ISOLATION: Train on first 75%, Validate on last 25%
        # This solves the "0 candles" error by not forcing a 2024 cutoff if data starts late
        cutoff_idx = int(len(df1) * 0.75)
        train_df1 = df1.iloc[:cutoff_idx].copy()
        
        start_d = train_df1['date'].min()
        end_d = train_df1['date'].max()
        
        print(f"✅ Isolated {len(train_df1)} training candles ({start_d.date()} to {end_d.date()})")
        return train_df1, df5, df15, dfh1

    def engineer_features(self, df1, df5, df15, dfh1):
        print("🛠️ Transforming raw data into Apex Intelligence (v4.0 High-Freq)...")
        df = df1.copy()
        
        # Multi-Timeframe Context Injection
        for name, cdf in [('m5', df5), ('m15', df15), ('h1', dfh1)]:
            cdf = cdf.copy()
            cdf[f'rsi_{name}'] = calculate_rsi(cdf['close'], 14)
            ma = cdf['close'].rolling(20).mean()
            cdf[f'trend_{name}'] = np.where(cdf['close'] > ma, 1, -1)
            cdf[f'vol_{name}'] = cdf['close'].pct_change().rolling(20).std()
            
            df = pd.merge_asof(df.sort_values('date'), cdf[['date', f'rsi_{name}', f'trend_{name}', f'vol_{name}']].sort_values('date'), 
                               on='date', direction='backward')

        # Advanced Micro-Scalping Features
        close = df['close']
        df['rsi'] = calculate_rsi(close, 14)
        df['rsi_slope'] = df['rsi'].diff(3)
        df['momentum'] = close.diff(5) / (close.shift(5) + 1e-9)
        
        # Volatility Squeeze Detection
        ma20, std20 = close.rolling(20).mean(), close.rolling(20).std()
        df['bb_width'] = (4*std20) / (ma20 + 1e-9)
        df['bb_pos'] = (close - (ma20 - 2*std20)) / (4*std20 + 1e-9)
        df['bb_slope'] = df['bb_width'].diff(3)
        
        # EMA Structure
        for s in [9, 21, 50, 200]:
            ma = close.rolling(s).mean()
            df[f'ema_{s}_dist'] = (close - ma) / (ma + 1e-9)
        
        df['ema_cross'] = (df['ema_9_dist'] - df['ema_21_dist'])
        df['atr'] = calculate_atr(df, 14)
        df['atr_norm'] = df['atr'] / (close + 1e-9)
        
        # Session Awareness
        df['hour'] = df['date'].dt.hour
        df['is_high_liquidity'] = ((df['hour'] >= 8) & (df['hour'] <= 11)) | ((df['hour'] >= 13) & (df['hour'] <= 16))
        
        self.features = [
            'rsi', 'rsi_slope', 'momentum', 'bb_width', 'bb_pos', 'bb_slope',
            'ema_9_dist', 'ema_21_dist', 'ema_50_dist', 'ema_200_dist', 'ema_cross',
            'atr_norm', 'is_high_liquidity',
            'rsi_m5', 'trend_m5', 'vol_m5', 'rsi_m15', 'trend_m15', 'rsi_h1', 'trend_h1'
        ]
        
        return df.replace([np.inf, -np.inf], 0).fillna(0)

    def label_data(self, df):
        """
        🚀 TARGET: 10+ Signals/Day | Precision Entry | Small Account Protection
        """
        print("🧠 Labeling for v4.0 | Target: 10+ Accurate Daily Signals...")
        horizon = 10 # 10-minute target window for definitive profit
        
        df['atr_val'] = calculate_atr(df, period=14)
        # Session-Adaptive Sensitivity: Be more aggressive during high-volume sessions
        df['sensitivity'] = np.where(df['is_high_liquidity'], 0.12, 0.18)
        df['atr_thresh'] = (df['atr_val'] * df['sensitivity']).rolling(3).mean()
        
        future_max = df['high'].rolling(horizon).max().shift(-horizon)
        future_min = df['low'].rolling(horizon).min().shift(-horizon)
        
        # Logic: 
        # 1. Reach TP (ATR Thresh) 
        # 2. Don't hit SL (ATR Thresh * 0.7) - Prioritize Small Account Survival
        # 3. Align with M5 Context
        buy_cond = (future_max - df['close'] > df['atr_thresh']) & \
                   (df['close'] - future_min < df['atr_thresh'] * 0.7) & \
                   (df['trend_m5'] >= 0)
                   
        sell_cond = (df['close'] - future_min > df['atr_thresh']) & \
                    (future_max - df['close'] < df['atr_thresh'] * 0.7) & \
                    (df['trend_m5'] <= 0)
        
        df['target'] = 0 
        df.loc[buy_cond, 'target'] = 1 
        df.loc[sell_cond, 'target'] = 2 
        
        # 🚫 CLEANUP: Reject signals during 3:00-7:00 AM (Low spread efficiency)
        df.loc[(df['hour'] >= 3) & (df['hour'] <= 6), 'target'] = 0
        
        return df.dropna()

    def train(self):
        print("\n" + "═"*60)
        print("🦁 GIA SIGNAL PRO v1.0.1: INSTITUTIONAL PRECISION")
        print("═"*60)
        
        df_train_raw, df5, df15, dfh1 = self.load_data()
        df = self.engineer_features(df_train_raw, df5, df15, dfh1)
        df = self.label_data(df)
        
        # Chronological Split (no data leakage)
        n = len(df)
        train_idx = int(n * 0.7)
        train_df = df.iloc[:train_idx]
        val_df = df.iloc[train_idx:]
        
        # ⚖️ BALANCING FOR FREQUENCY: 3:1 Signal Ratio
        # We sample 'Wait' to be fewer than signals to force the model to look for opportunities
        skip = train_df[train_df['target'] == 0]
        buy = train_df[train_df['target'] == 1]
        sell = train_df[train_df['target'] == 2]
        
        print(f"📈 Raw Targets: Buy: {len(buy)} | Sell: {len(sell)} | Skip: {len(skip)}")
        
        target_skip_size = int((len(buy) + len(sell)) / 3.0)
        skip_sampled = skip.sample(n=min(len(skip), target_skip_size), random_state=42)
        
        final_train = pd.concat([skip_sampled, buy, sell]).sample(frac=1.0, random_state=42)
        X_train, y_train = final_train[self.features], final_train['target']
        X_val, y_val = val_df[self.features], val_df['target']
        
        weights = compute_sample_weight('balanced', y_train)
        
        # 🧠 NUCLEAR DEEP BOOSTING (v1.0.1 Config)
        model = xgb.XGBClassifier(
            max_depth=7,
            learning_rate=0.012,
            n_estimators=5000,
            objective='multi:softprob',
            num_class=3,
            tree_method='hist',
            subsample=0.85,
            colsample_bytree=0.85,
            gamma=0.1,
            min_child_weight=2,
            reg_alpha=0.1, # L1 Regularization to prevent noise-fitting
            reg_lambda=1.0, # L2 Regularization
            random_state=42
        )
        
        print("🛠️ Phase 1: Training Deep Sniper Core...")
        model.fit(X_train, y_train, sample_weight=weights, 
                  eval_set=[(X_val, y_val)], early_stopping_rounds=150, verbose=100)
        
        print("⚖️ Initializing High-Resolution Calibration...")
        calibrator = ConfidenceCalibrator()
        val_probs = model.predict_proba(val_df[self.features])
        calibrator.fit(val_probs, val_df['target'].values)
        
        save_data = {
            'model': model,
            'calibrator': calibrator,
            'features': self.features,
            'label_encoder': MockEncoder(),
            'metadata': {
                'version': '1.0.1',
                'mode': 'Small Account High-Freq',
                'trained_until': '2023-12-31',
                'training_size': len(X_train)
            }
        }
        
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        joblib.dump(save_data, MODEL_PATH)
        print(f"✅ GIA_SIGNAL_PRO v1.0.1 SAVED: {MODEL_PATH}")

if __name__ == "__main__":
    trainer = GIA_Apex_Distiller()
    trainer.train()
