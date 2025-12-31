
import os
import sys
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import json
from datetime import datetime
from sklearn.utils.class_weight import compute_sample_weight

# Fix path for package imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from backend.engine.backtest import BacktestEngine
from backend.core.regime import MarketRegimeEngine

class MockEncoder:
    def inverse_transform(self, idxs):
        mapping = {0: 'WAIT', 1: 'BUY', 2: 'SELL'}
        return [mapping[i] for i in idxs]

class GIA_v1_1_MultiFrame_Trainer:
    """
    🦁 GIA v1.1 PRO - OMNI-TIMEFRAME INTELLIGENCE
    ---------------------------------------------
    Fusion: M15 (Tactical) + M30 (Confirmation) + H1 (Stragetic Trend).
    Goal: Outperform v14 by seeing the "Big Picture".
    """

    def __init__(self):
        # 360-Degree Vision Feature Set
        self.features = [
            # --- M15 TACTICAL (v14 Core) ---
            'rsi', 'rsi_slope', 'mom_5', 'mom_10', 'vol_20',
            'bb_pos', 'bb_width', 'macd_norm', 
            'ema_9_dist', 'ema_21_dist', 'ema_50_dist',
            'body_size', 'upper_wick', 'lower_wick', 'regime_flag',
            
            # --- M30 CONFIRMATION ---
            'rsi_m30', 'macd_m30', 'bb_width_m30',
            
            # --- H1 STRATEGIC TREND ---
            'ema_200_dist_h1', 'rsi_h1', 'mom_h1', 'trend_h1'
        ]
        
        # Enhanced Params for Larger Feature Space
        self.params = {
            'max_depth': 7,          # Deeper trees to handle interaction between timeframes
            'learning_rate': 0.015,
            'n_estimators': 1500,
            'subsample': 0.8,
            'colsample_bytree': 0.8, # Select 80% features (forces mixing MTF features)
            'reg_alpha': 1.0,
            'reg_lambda': 3.0,
            'objective': 'multi:softmax',
            'num_class': 3,
            'tree_method': 'hist',
            'random_state': 42
        }
        
        self.models_dir = os.path.join(PROJECT_ROOT, 'backend', 'models')
        os.makedirs(self.models_dir, exist_ok=True)

    def load_and_merge_data(self):
        """
        Loads M15, M30, H1 and merges them into a single Master Dataset.
        """
        data_dir = os.path.join(PROJECT_ROOT, 'backend', 'hestory')
        
        print("📂 Loading M15 (Primary)...")
        df_m15 = self._load_csv(os.path.join(data_dir, 'XAUUSD_M15.csv'))
        
        print("📂 Loading M30 (Confirmation)...")
        df_m30 = self._load_csv(os.path.join(data_dir, 'XAUUSD_M30.csv'))
        df_m30 = self._engineer_secondary(df_m30, 'm30')
        
        print("📂 Loading H1 (Strategic)...")
        df_h1 = self._load_csv(os.path.join(data_dir, 'XAUUSD_H1.csv'))
        df_h1 = self._engineer_secondary(df_h1, 'h1')
        
        print("🔗 Merging Timeframes (Fusion)...")
        # Merge on 'date' - Forward fill H1/M30 data to align with M15 candles
        # Note: In live trading, H1 data repeats for four M15 candles.
        
        merged = pd.merge_asof(df_m15.sort_values('date'), df_m30.sort_values('date'), on='date', direction='backward')
        merged = pd.merge_asof(merged.sort_values('date'), df_h1.sort_values('date'), on='date', direction='backward')
        
        return merged.dropna()

    def _load_csv(self, path):
        df = pd.read_csv(path)
        df.columns = [c.lower() for c in df.columns]
        if 'time' in df.columns:
            df['date'] = pd.to_datetime(df['time'], format='%m/%d/%Y %I:%M:%S %p')
        else:
            df['date'] = pd.to_datetime(df.index)
        return df

    def _engineer_secondary(self, df, suffix):
        """
        Calculates key indicators for higher timeframes and renames cols.
        """
        df = df.copy()
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df[f'rsi_{suffix}'] = 100 - (100 / (1 + rs))
        
        # MACD
        e12 = df['close'].ewm(span=12).mean()
        e26 = df['close'].ewm(span=26).mean()
        df[f'macd_{suffix}'] = (e12 - e26) / df['close']
        
        # BB Width (Volatility)
        ma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df[f'bb_width_{suffix}'] = ((ma + 2*std) - (ma - 2*std)) / ma
        
        # H1 Specific Trend
        if suffix == 'h1':
            df[f'ema_200_{suffix}'] = df['close'].ewm(span=200).mean()
            df[f'ema_200_dist_{suffix}'] = (df['close'] - df[f'ema_200_{suffix}']) / df['close']
            df[f'mom_{suffix}'] = df['close'].pct_change(4) # 4 hours momentum
            # Binary Trend Flag
            df[f'trend_{suffix}'] = np.where(df['close'] > df[f'ema_200_{suffix}'], 1, -1)
            
        # Select only needed columns + date
        keep_cols = ['date'] + [c for c in df.columns if c.endswith(suffix)]
        return df[keep_cols]

    def engineer_primary_m15(self, df):
        """Standard v14+ Features for M15"""
        df = df.copy()
        
        # Indicators
        df['rsi'] = self._calc_rsi(df['close'])
        df['rsi_slope'] = df['rsi'].diff(3)
        df['mom_5'] = df['close'].pct_change(5)
        df['mom_10'] = df['close'].pct_change(10)
        df['vol_20'] = df['close'].rolling(20).std()
        
        # BB
        ma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df['bb_width'] = ((ma + 2*std) - (ma - 2*std)) / ma
        df['bb_pos'] = (df['close'] - (ma - 2*std)) / (4*std)
        
        # EMAs
        for s in [9, 21, 50]:
            ema = df['close'].ewm(span=s).mean()
            df[f'ema_{s}_dist'] = (df['close'] - ema) / ema
            
        # MACD
        e12 = df['close'].ewm(span=12).mean()
        e26 = df['close'].ewm(span=26).mean()
        df['macd_norm'] = (e12 - e26) / df['close']
        
        # Candles
        df['body_size'] = (df['close'] - df['open']).abs() / df['close']
        df['upper_wick'] = (df['high'] - df[['open', 'close']].max(axis=1)) / df['close']
        df['lower_wick'] = (df[['open', 'close']].min(axis=1) - df['low']) / df['close']
        
        # Regime (v1.1)
        re = MarketRegimeEngine()
        df = re.classify(df)
        
        return df

    def _calc_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def create_labels(self, df):
        """0.2% Move Target (v14 Standard)"""
        df = df.copy()
        THRESHOLD = 0.002 
        HORIZON = 12
        
        df['fwd_max'] = df['close'].rolling(HORIZON).max().shift(-HORIZON)
        df['fwd_min'] = df['close'].rolling(HORIZON).min().shift(-HORIZON)
        
        conditions = [
            (df['fwd_max'] > df['close'] * (1 + THRESHOLD)), 
            (df['fwd_min'] < df['close'] * (1 - THRESHOLD))
        ]
        df['target'] = np.select(conditions, [1, 2], default=0)
        return df.dropna()

    def train(self, df):
        print("\n" + "🌎"*35)
        print("🚀 GIA v1.1 MFT (Multi-Frame Tech) TRAINING STARTED")
        print("🌎"*35)
        
        # Train on Modern Era (2018-2023)
        train_df = df[(df['date'].dt.year >= 2018) & (df['date'].dt.year <= 2023)].copy()
        test_df = df[df['date'].dt.year >= 2024].copy()
        
        print(f"📊 Training: {len(train_df):,} | Test (2024+): {len(test_df):,}")
        
        X_train = train_df[self.features]
        y_train = train_df['target']
        weights = compute_sample_weight('balanced', y_train)
        
        print("⚙️  Training XGBoost with Omni-View...")
        model = xgb.XGBClassifier(**self.params)
        model.fit(X_train, y_train, sample_weight=weights, verbose=True)
        
        final_path = os.path.join(self.models_dir, 'GIA_v1.1_PRO.pkl')
        joblib.dump({
            'model': model, 
            'feature_columns': self.features, 
            'label_encoder': MockEncoder()
        }, final_path)
        print(f"✅ Model Saved: {final_path}")
        
        if not test_df.empty:
            print("\n📈 Validating on 2024-2025...")
            engine = BacktestEngine(model_path=final_path)
            engine.load_model()
            res = engine.backtest(test_df, broker_name='SURVIVAL', risk_pct=0.5)
            
            print(f"\n🏆 MULTI-FRAME PERFORMANCE (2024-2025):")
            print(f"   Profit Factor: {res.get('profit_factor', 0):.2f}")
            print(f"   Max Drawdown:  {res.get('max_drawdown', 0):.2f}%")
            print(f"   Net Profit:    {res.get('net_profit_pct', 0):.2f}%")

def run_training():
    trainer = GIA_v1_1_MultiFrame_Trainer()
    
    # 1. Load & Merge
    df = trainer.load_and_merge_data()
    
    # 2. Engineer Primary (M15)
    print("🛠️ Engineering Primary M15 Features...")
    df = trainer.engineer_primary_m15(df)
    
    # 3. Label & Train
    print("🏷️ Creating Labels...")
    df = trainer.create_labels(df)
    
    trainer.train(df)

if __name__ == "__main__":
    run_training()
