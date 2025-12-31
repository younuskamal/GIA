
import os
import sys
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import json
import traceback
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

class GIA_v2_Hybrid_Trainer:
    """
    🦁 GIA v2 PRO - THE HYBRID EVOLUTION
    -----------------------------------
    Merge v1.1 Intelligence + v14 Discipline.
    Objective: Total Market Dominance.
    """

    def __init__(self):
        # 360-Degree Vision + Volatility Sensitivity
        self.features = [
            # --- M15 TACTICAL ---
            'rsi', 'rsi_slope', 'mom_5', 'mom_10', 'vol_20',
            'bb_pos', 'bb_width', 'macd_norm', 
            'ema_9_dist', 'ema_21_dist', 'ema_50_dist',
            'body_size', 'upper_wick', 'lower_wick', 'regime_flag',
            
            # --- M30 CONFIRMATION ---
            'rsi_m30', 'macd_m30', 'bb_width_m30',
            
            # --- H1 STRATEGIC ---
            'ema_200_dist_h1', 'rsi_h1', 'mom_h1', 'trend_h1',
            
            # --- NEW V2 HYBRID FEATURES ---
            'atr_norm', 'vol_ratio', 'price_dist_bb'
        ]
        
        self.models_dir = os.path.join(PROJECT_ROOT, 'backend', 'models')
        os.makedirs(self.models_dir, exist_ok=True)

    def load_full_data(self):
        data_dir = os.path.join(PROJECT_ROOT, 'backend', 'hestory')
        print("📂 Loading Multi-Timeframe Datasets...")
        
        df_m15 = self._load_csv(os.path.join(data_dir, 'XAUUSD_M15.csv'))
        df_m30 = self._load_csv(os.path.join(data_dir, 'XAUUSD_M30.csv'))
        df_h1 = self._load_csv(os.path.join(data_dir, 'XAUUSD_H1.csv'))
        
        # Engineering MTF
        m30_eng = self._engineer_mtf(df_m30, 'm30')
        h1_eng = self._engineer_mtf(df_h1, 'h1')
        
        merged = pd.merge_asof(df_m15.sort_values('date'), m30_eng.sort_values('date'), on='date', direction='backward')
        merged = pd.merge_asof(merged.sort_values('date'), h1_eng.sort_values('date'), on='date', direction='backward')
        
        return merged.dropna()

    def _load_csv(self, path):
        df = pd.read_csv(path)
        df.columns = [c.lower() for c in df.columns]
        if 'time' in df.columns:
            df['date'] = pd.to_datetime(df['time'], format='%m/%d/%Y %I:%M:%S %p')
        else:
            df['date'] = pd.to_datetime(df.index)
        return df

    def _engineer_mtf(self, df, suffix):
        df = df.copy()
        # Indicators
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df[f'rsi_{suffix}'] = 100 - (100 / (1 + (gain/loss)))
        
        e12 = df['close'].ewm(span=12).mean()
        e26 = df['close'].ewm(span=26).mean()
        df[f'macd_{suffix}'] = (e12 - e26) / df['close']
        
        ma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df[f'bb_width_{suffix}'] = (4*std) / ma
        
        if suffix == 'h1':
            ema200 = df['close'].ewm(span=200).mean()
            df['ema_200_dist_h1'] = (df['close'] - ema200) / df['close']
            df['mom_h1'] = df['close'].pct_change(4)
            df['trend_h1'] = np.where(df['close'] > ema200, 1, -1)
            
        keep = ['date'] + [c for c in df.columns if c.endswith(suffix) or c.endswith('_h1')]
        return df[keep]


    def _calc_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        return 100 - (100 / (1 + (gain/loss)))

    def _calc_atr(self, df, period=14):
        h_l = df['high'] - df['low']
        h_pc = (df['high'] - df['close'].shift()).abs()
        l_pc = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def engineer_primary(self, df):
        df = df.copy()
        
        # 1. Base Intelligence
        df['rsi'] = self._calc_rsi(df['close'])
        df['rsi_slope'] = df['rsi'].diff(3)
        df['mom_5'] = df['close'].pct_change(5)
        df['vol_20'] = df['close'].rolling(20).std()
        
        e12 = df['close'].ewm(span=12).mean()
        e26 = df['close'].ewm(span=26).mean()
        df['macd_norm'] = (e12 - e26) / (df['close'] + 1e-6)
        
        # Power & Volatility
        avg_body = (df['close'] - df['open']).abs().rolling(20).mean()
        df['body_rel'] = (df['close'] - df['open']).abs() / (avg_body + 1e-6)
        
        for s in [21, 50, 200]:
            ema = df['close'].ewm(span=s).mean()
            df[f'ema_{s}_dist'] = (df['close'] - ema) / (ema + 1e-6)
            
        df['ribbon_align'] = (np.sign(df['ema_21_dist']) + np.sign(df['ema_50_dist']) + np.sign(df['ema_200_dist'])) / 3.0

        ma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df['bb_width'] = (4*std) / (ma + 1e-6)
        df['bb_pos'] = (df['close'] - (ma - 2*std)) / (4*std + 1e-6)
        
        df['velocity'] = df['close'].diff(5) / (df['vol_20'] + 1e-6)
        df['coiling'] = df['bb_width'] / (df['bb_width'].rolling(50).mean() + 1e-6)
        
        # Candle Geometry
        df['upper_wick'] = (df['high'] - df[['open', 'close']].max(axis=1)) / (df['close'] + 1e-6)
        df['lower_wick'] = (df[['open', 'close']].min(axis=1) - df['low']) / (df['close'] + 1e-6)
        df['wick_ratio'] = (df['upper_wick'] - df['lower_wick']) / (df['upper_wick'] + df['lower_wick'] + 1e-6)
        
        df['trend_harmony'] = (
            np.sign(df['macd_norm']) + 
            np.sign(df.get('macd_m30', 0)) + 
            np.sign(df.get('macd_h1', 0))
        ) / 3.0
        
        df['hour'] = df['date'].dt.hour
        df['is_peak'] = ((df['hour'] >= 7) & (df['hour'] <= 22)).astype(int)
        df['is_peak_hour'] = df['is_peak'] # Sync
        
        atr = self._calc_atr(df)
        df['atr_norm'] = atr / (df['close'] + 1e-6)
        df['vol_regime'] = (df['vol_20'] / df['vol_20'].rolling(200).mean()).fillna(1.0)
        
        re = MarketRegimeEngine()
        df = re.classify(df)
        
        # 🛑 ULTIMATE CLEANING: XGBoost will fail on Inf/-Inf
        df = df.replace([np.inf, -np.inf], np.nan)
        return df.dropna()

    def create_labels(self, df):
        df = df.copy()
        # 🦁 ULTRA APEX SCALPING: 1.4x ATR (Aggressive Frequency)
        atr = self._calc_atr(df)
        horizon = 15 # Extended horizon for smarter exits
        
        fwd_max = df['close'].rolling(horizon).max().shift(-horizon)
        fwd_min = df['close'].rolling(horizon).min().shift(-horizon)
        
        # Threshold: 1.4x ATR (The Sweet Spot for Scalpers)
        threshold = atr * 1.4 
        
        buy_cond = (fwd_max >= df['close'] + threshold)
        sell_cond = (fwd_min <= df['close'] - threshold)
        
        df['target'] = 0
        df.loc[buy_cond, 'target'] = 1
        df.loc[sell_cond, 'target'] = 2
        df.loc[buy_cond & sell_cond, 'target'] = 0 
        
        return df.dropna()

    def _calculate_extended_stats(self, res):
        trades = pd.DataFrame(res['trades'])
        if trades.empty:
            res.update({'sharpe': 0, 'calmar': 0, 'max_win': 0, 'max_loss': 0, 'total_trades': 0})
            return res
        
        trades['entry_date'] = pd.to_datetime(trades['entry_date'])
        daily = trades.set_index('entry_date')['pnl_net'].resample('D').sum()
        std = daily.std()
        res['sharpe'] = (daily.mean() / std * np.sqrt(252)) if std > 0 else 0
        res['calmar'] = (res['net_profit_pct'] / res['max_drawdown']) if res['max_drawdown'] > 0 else 0
        res['max_win'] = trades['pnl_net'].max()
        res['max_loss'] = trades['pnl_net'].min()
        
        return res

    def evolutionary_training(self, full_df):
        print("\n" + "👹"*35)
        print("🚀 GIA v2 PRO - ULTRA-APEX PRO (FINAL DOMINANCE)")
        print("👹"*35)
        
        # Strict Split: Train (<2023) | Val (2023-2025)
        train_df = full_df[full_df['date'].dt.year < 2023].copy()
        val_df = full_df[full_df['date'].dt.year >= 2023].copy()
        
        print(f"📊 Dataset: Train={len(train_df):,} | Val (2023-2025)={len(val_df):,}")
        
        v2_new = ['is_peak', 'is_peak_hour', 'coiling', 'velocity', 'trend_harmony', 'wick_ratio', 'vol_regime', 'ribbon_align', 'body_rel']
        features_to_use = sorted(list(set(self.features + v2_new)))
        # Clean sync with engineering list
        features_to_use = [f for f in features_to_use if f in train_df.columns]
        
        X_train = train_df[features_to_use]
        y_train = train_df['target']
        weights = compute_sample_weight('balanced', y_train)
        
        # Ultra Genomes: Faster Learning
        configs = [
            {'max_depth': 8, 'learning_rate': 0.015, 'n_estimators': 3000, 'subsample': 0.8, 'colsample_bytree': 0.8, 'reg_alpha': 2.0, 'reg_lambda': 10.0, 'gamma': 1.0}, 
            {'max_depth': 6, 'learning_rate': 0.02, 'n_estimators': 2500, 'subsample': 0.7, 'colsample_bytree': 0.7, 'reg_alpha': 5.0, 'reg_lambda': 20.0, 'gamma': 2.5},
            {'max_depth': 9, 'learning_rate': 0.01,  'n_estimators': 3500, 'subsample': 0.9, 'colsample_bytree': 0.6, 'reg_alpha': 1.0, 'reg_lambda': 5.0, 'gamma': 0.5}
        ]
        
        best_fitness = -1e9
        best_model_path = None
        best_stats = {}
        
        for i, cfg in enumerate(configs):
            print(f"\n🧪 ULTRA GENOME #{i+1} | Depth: {cfg['max_depth']} | LR: {cfg['learning_rate']}")
            model = xgb.XGBClassifier(**cfg, objective='multi:softmax', num_class=3, tree_method='hist')
            model.fit(X_train, y_train, sample_weight=weights)
            
            temp_path = os.path.join(self.models_dir, f'GIA_v2_ULTRA_{i}.pkl')
            joblib.dump({
                'model': model, 
                'feature_columns': features_to_use, 
                'label_encoder': MockEncoder()
            }, temp_path)
            
            engine = BacktestEngine(model_path=temp_path)
            engine.load_model()
            # Test in strict SURVIVAL environment
            res = engine.backtest(val_df, broker_name='SURVIVAL', initial_balance=500, risk_pct=1.0)
            
            if "error" in res:
                continue
            
            res = self._calculate_extended_stats(res)
            
            pf = res.get('profit_factor', 0)
            dd = res.get('max_drawdown', 100)
            trades = res.get('total_trades', 0)
            roi = res.get('net_profit_pct', 0)
            
            # FITNESS for total dominance
            fitness = (roi * 0.5) + (trades * 10.0) + (pf * 1000) - (dd * 500)
            
            print(f"   📊 Results: ROI={roi:,.1f}% | PF={pf:.2f} | DD={dd:.1f}% | Trades={trades}")
            
            if fitness > best_fitness:
                best_fitness = fitness
                best_model_path = temp_path
                best_stats = res

        if best_model_path:
            final_path = os.path.join(self.models_dir, 'GIA_v2_FLASH.pkl')
            # Copy winner to final
            winner = joblib.load(best_model_path)
            joblib.dump(winner, final_path)
            print(f"\n🏆 CHAMPION SELECTED: {final_path}")
            return best_stats
        else:
            print("\n❌ FAILED TO PRODUCE ELITE MODEL. RETRYING WITH DEEPER HYBRIDS...")
            return None

def run_v2_training():
    trainer = GIA_v2_Hybrid_Trainer()
    
    # 1. MTF Loading
    df = trainer.load_full_data()
    
    # 2. Engineering
    print("🛠️ Engineering Hybrid Features...")
    df = trainer.engineer_primary(df)
    
    # 3. Hybrid Labeling
    print("🏷️ Creating V2 High-Confidence Labels...")
    df = trainer.create_labels(df)
    
    # 4. Evolutionary Loop
    stats = trainer.evolutionary_training(df)
    
    if stats:
        print("\n" + "⚡"*35)
        print("🦁 GIA_v2_FLASH TRAINING COMPLETE")
        print(f"   Net Profit:    {stats['net_profit_pct']:.2f}%")
        print(f"   Profit Factor: {stats['profit_factor']:.2f}")
        print(f"   Max Drawdown:  {stats['max_drawdown']:.2f}%")
        print(f"   Total Trades:  {stats['total_trades']}")
        print("⚡"*35)
    else:
        print("\n❌ Evolution Failed to meet the User's Elite standards.")

if __name__ == "__main__":
    run_v2_training()
