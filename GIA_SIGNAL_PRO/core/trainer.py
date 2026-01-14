
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
        
        # 🚀 Institutional High-Intelligence Features (Direct Injection)
        df['velocity'] = close.diff(1) / (close.shift(1) + 1e-9)
        df['acceleration'] = df['velocity'].diff(1)
        
        # VSA Logic: Volume/Price Spread Analysis
        df['vol_delta'] = df['volume'] * np.sign(close - df['open'])
        df['vol_momentum'] = df['vol_delta'].rolling(5).mean() / (df['volume'].rolling(20).mean() + 1e-9)
        
        df['liquidity_shock'] = df['volume'] / (df['volume'].rolling(20).mean() + 1e-9)
        
        # Market Entropy (Efficiency Ratio)
        diff_sum = close.diff().abs().rolling(10).sum()
        range_sum = (df['high'].rolling(10).max() - df['low'].rolling(10).min() + 1e-9)
        df['market_entropy'] = diff_sum / range_sum

        df['atr'] = calculate_atr(df, 14)
        df['atr_norm'] = df['atr'] / (close + 1e-9)
        
        # 🕯️ Candle Anatomy IQ
        df['body_size'] = (df['close'] - df['open']).abs()
        df['wick_size'] = (df['high'] - df['low']) - df['body_size']
        df['candle_strength'] = df['body_size'] / (df['high'] - df['low'] + 1e-9)
        
        # 📏 Distance Logic (Mean Reversion Awareness)
        ma9 = close.rolling(9).mean()
        df['dist_ma9'] = (close - ma9) / (ma9 + 1e-9)
        
        # 🌍 Regime Intel
        df = self.regime_engine.classify(df) # Adds 'regime_flag'
        
        # Session Awareness
        df['hour'] = df['date'].dt.hour
        df['is_high_liquidity'] = ((df['hour'] >= 8) & (df['hour'] <= 11)) | ((df['hour'] >= 13) & (df['hour'] <= 16))
        
        self.features = [
            'rsi', 'rsi_slope', 'momentum', 'bb_width', 'bb_pos', 'bb_slope',
            'ema_9_dist', 'ema_21_dist', 'ema_50_dist', 'ema_200_dist',
            'atr_norm', 'is_high_liquidity',
            'rsi_m5', 'trend_m5', 'vol_m5', 'rsi_m15', 'trend_m15', 'rsi_h1', 'trend_h1',
            'velocity', 'acceleration', 'liquidity_shock', 'market_entropy',
            'candle_strength', 'dist_ma9', 'regime_flag', 'vol_momentum'
        ]
        
        # 🧪 Add Lags for Temporal IQ (What happened in the last 3 minutes?)
        for feat in ['velocity', 'candle_strength', 'vol_momentum']:
            for lag in [1, 2, 3]:
                df[f'{feat}_lag{lag}'] = df[feat].shift(lag)
                self.features.append(f'{feat}_lag{lag}')
        
        return df.replace([np.inf, -np.inf], 0).fillna(0)

    def label_data(self, df):
        """
        🚀 TARGET: Abrasive Institutional Labeling (v5.0)
        Only signals that SURVIVE spread, commission, and slippage are labeled.
        """
        print("🧠 Labeling with Hyper-Frequency Pulse (UHF Mode)...")
        horizon = 2 # Hyper-Pulse: 2-minute pulse capture
        friction = 0.01 
        
        df['atr_val'] = calculate_atr(df, period=14)
        # Pulse Targets: Capture any movement >= 0.01 (1 Gold Pip)
        df['min_target'] = 0.01
        
        future_max = df['high'].rolling(horizon).max().shift(-horizon)
        future_min = df['low'].rolling(horizon).min().shift(-horizon)
        
        # Logic: 
        # 1. Potential Gain - Friction > Min Target
        # 2. Risk (Max Adverse Excursion) < Min Target * 1.5 (High tolerance for UHF)
        # 3. Universal Momentum (No Trend Filter)
        buy_cond = ((future_max - df['close']) - friction > df['min_target']) & \
                   (df['close'] - future_min < df['min_target'] * 1.5) & \
                   (df['trend_m5'] >= -4.0)
                   
        sell_cond = ((df['close'] - future_min) - friction > df['min_target']) & \
                    (future_max - df['close'] < df['min_target'] * 1.5) & \
                    (df['trend_m5'] <= 4.0)
        
        df['target'] = 0 
        df.loc[buy_cond, 'target'] = 1 
        df.loc[sell_cond, 'target'] = 2 
        
        # 🟢 Universal 24/7 Access: No hour filters for UHF
        
        signals = len(df[df['target'] != 0])
        print(f"✅ GIA Intelligence: Extracted {signals} signals that survive friction.")
        
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
        
        # ⚖️ Dynamic Balancing: Ensure 'Wait' doesn't overwhelm the model
        # Target a 1:1 ratio between signals and wait to make the model "sharp"
        target_skip_size = len(buy) + len(sell)
        skip_sampled = skip.sample(n=min(len(skip), target_skip_size), random_state=42)
        
        final_train = pd.concat([skip_sampled, buy, sell]).sample(frac=1.0, random_state=42)
        # ⚖️ UHF Predator Balancing (v11.0)
        # We use heavy weighting to force signal detection for high-frequency density
        X_train, y_train = final_train[self.features], final_train['target']
        X_val, y_val = val_df[self.features], val_df['target']
        
        # 5:1 Weighting: Signals are 5x more important than 'Wait'
        weights = np.ones(len(y_train))
        weights[y_train == 1] = 5.0
        weights[y_train == 2] = 5.0
        weights[y_train == 0] = 1.0
        
        # 🧠 NUCLEAR DEEP SNIPER BOOSTING (v11.0 - Predator Edition)
        model = xgb.XGBClassifier(
            max_depth=10,            # Deeper trees for micro-burst detection
            learning_rate=0.02,      # Faster learning for pulse patterns
            n_estimators=12000,      # Massive ensemble for stability
            objective='multi:softprob',
            num_class=3,
            tree_method='hist',
            subsample=0.9,           # Higher sample usage for UHF
            colsample_bytree=0.9,
            gamma=0.05,
            min_child_weight=1,      # Max sensitivity to micro-clusters
            reg_alpha=0.1,
            reg_lambda=0.5,
            max_delta_step=5,        # High stability for heavy weighting
            early_stopping_rounds=150, # Moved to constructor for XGBoost 2.0+
            random_state=42
        )
        
        print(f"🛠️ Phase 1: Training Predator UHF Core on {len(X_train)} pulses...")
        model.fit(X_train, y_train, sample_weight=weights, 
                  eval_set=[(X_val, y_val)], verbose=100)
        
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
                'version': '1.0.2',
                'mode': 'Institutional Abrasive (High-Friction Resistance)',
                'trained_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'training_size': len(X_train)
            }
        }
        
        PREDATOR_PATH = MODELS_DIR / "GIA_SIGNAL_PREDATOR.pkl"
        LIVE_PRO_PATH = PROJECT_ROOT / "backend" / "models" / "GIA_v2_PRO.pkl"
        
        os.makedirs(os.path.dirname(PREDATOR_PATH), exist_ok=True)
        os.makedirs(os.path.dirname(LIVE_PRO_PATH), exist_ok=True)
        
        # Save to both locations
        joblib.dump(save_data, PREDATOR_PATH)
        joblib.dump(save_data, LIVE_PRO_PATH)
        
        print(f"✅ GIA_SIGNAL_PREDATOR v1.0.1 SAVED: {PREDATOR_PATH}")
        print(f"🧠 NEURAL LINK: Live PRO model updated at {LIVE_PRO_PATH}")

if __name__ == "__main__":
    trainer = GIA_Apex_Distiller()
    trainer.train()
