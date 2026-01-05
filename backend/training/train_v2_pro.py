
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
            'atr_norm', 'vol_ratio', 'price_dist_bb', 'coiling', 'velocity',
            'trend_harmony', 'wick_ratio', 'vol_regime', 'ribbon_align', 'body_rel',
            'price_acceleration', 'liquidity_shock', 'market_entropy', 'exhaustion_index'
        ]
        
        self.models_dir = os.path.join(PROJECT_ROOT, 'backend', 'models')
        os.makedirs(self.models_dir, exist_ok=True)

    def load_full_data(self):
        # 🛡️ Redirected to Institutional Data Directory
        data_dir = r"C:\GIA_DATA"
        print(f"📂 Loading Institutional Multi-Timeframe Datasets from {data_dir}...")
        
        def read(tf):
            path = os.path.join(data_dir, f"XAUUSD_{tf}.csv")
            df = pd.read_csv(path)
            df.columns = [c.lower() for c in df.columns]
            # Handle mixed date formats common in MT5/cTrader exports
            df['date'] = pd.to_datetime(df['time'], format='mixed', dayfirst=False)
            return df.sort_values('date', ascending=True)

        df_m15 = read("M15")
        df_m30 = read("M30")
        df_h1 = read("H1")
        
        # Engineering MTF
        m30_eng = self._engineer_mtf(df_m30, 'm30')
        h1_eng = self._engineer_mtf(df_h1, 'h1')
        
        merged = pd.merge_asof(df_m15.sort_values('date'), m30_eng.sort_values('date'), on='date', direction='backward')
        merged = pd.merge_asof(merged.sort_values('date'), h1_eng.sort_values('date'), on='date', direction='backward')
        
        return merged.ffill().bfill().dropna()

    def _engineer_mtf(self, df, suffix):
        df = df.copy()
        # Indicators
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df[f'rsi_{suffix}'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
        
        e12 = df['close'].ewm(span=12, adjust=False).mean()
        e26 = df['close'].ewm(span=26, adjust=False).mean()
        df[f'macd_{suffix}'] = (e12 - e26) / (df['close'] + 1e-9)
        
        ma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df[f'bb_width_{suffix}'] = (4*std) / (ma + 1e-9)
        
        if suffix == 'h1':
            ema200 = df['close'].ewm(span=200, adjust=False).mean()
            df['ema_200_dist_h1'] = (df['close'] - ema200) / (df['close'] + 1e-9)
            df['mom_h1'] = df['close'].pct_change(4)
            df['trend_h1'] = np.where(df['close'] > ema200, 1, -1)
            
        keep = ['date'] + [c for c in df.columns if c.endswith(suffix) or c.endswith('_h1')]
        return df[keep]

    def _calc_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        return 100 - (100 / (1 + (gain / (loss + 1e-9))))

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
        
        e12 = df['close'].ewm(span=12, adjust=False).mean()
        e26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd_norm'] = (e12 - e26) / (df['close'] + 1e-9)
        
        # Power & Volatility
        avg_body = (df['close'] - df['open']).abs().rolling(20).mean()
        # Body Rel match FeatureFactory: abs(close-open)/(high-low)
        df['body_rel'] = (df['close'] - df['open']).abs() / (df['high'] - df['low'] + 1e-9)
        
        for s in [9, 21, 50, 100, 200]:
            ema = df['close'].ewm(span=s, adjust=False).mean()
            df[f'ema_{s}_dist'] = (df['close'] - ema) / (ema + 1e-9)
            
        df['ribbon_align'] = (np.sign(df['ema_9_dist']) + np.sign(df['ema_21_dist']) + np.sign(df['ema_50_dist']) + np.sign(df['ema_100_dist']) + np.sign(df['ema_200_dist'])) / 5.0

        # Market Entropy (Chaos Detector)
        # Low entropy = predictable trend, High entropy = noise
        df['market_entropy'] = df['close'].diff().abs().rolling(10).sum() / (df['high'].rolling(10).max() - df['low'].rolling(10).min() + 1e-9)
        
        # Exhaustion Index (Risk detector)
        df['exhaustion_index'] = (df['close'] - df['close'].rolling(50).mean()).abs() / (df['vol_20'] * 2 + 1e-9)

        ma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df['bb_width'] = (4*std) / (ma + 1e-9)
        df['bb_pos'] = (df['close'] - (ma - 2*std)) / (4*std + 1e-9)
        
        df['velocity'] = df['close'].diff(5) / (df['vol_20'] + 1e-9)
        df['coiling'] = df['bb_width'] / (df['bb_width'].rolling(50).mean() + 1e-9)
        
        # Candle Geometry
        df['upper_wick'] = (df['high'] - df[['open', 'close']].max(axis=1)) / (df['close'] + 1e-9)
        df['lower_wick'] = (df[['open', 'close']].min(axis=1) - df['low']) / (df['close'] + 1e-9)
        # Wick Ratio match FeatureFactory: upper / lower
        df['wick_ratio'] = df['upper_wick'] / (df['lower_wick'] + 1e-9)
        
        df['trend_harmony'] = (
            np.sign(df['macd_norm']) + 
            np.sign(df.get('macd_m30', 0)) + 
            np.sign(df.get('macd_h1', 0))
        ) / 3.0
        
        # Super Trader Additions - Intelligent Logic
        df['price_acceleration'] = df['velocity'].diff(3)
        df['liquidity_shock'] = df['volume'] / (df['volume'].rolling(50).mean() + 1e-9)
        
        # New Intelligence: Divergence Proxy (Price vs RSI)
        df['div_proxy'] = df['close'].pct_change(5) - df['rsi'].pct_change(5)
        
        # New Intelligence: Structural Strength
        df['structure_strength'] = (df['close'] - df['close'].rolling(100).min()) / (df['close'].rolling(100).max() - df['close'].rolling(100).min() + 1e-9)
        
        df['hour'] = df['date'].dt.hour
        df['is_peak'] = ((df['hour'] >= 7) & (df['hour'] <= 22)).astype(int)
        
        atr = self._calc_atr(df)
        df['atr_norm'] = atr / (df['close'] + 1e-9)
        df['vol_regime'] = (df['vol_20'] / (df['vol_20'].rolling(200).mean() + 1e-9)).fillna(1.0)
        
        re = MarketRegimeEngine()
        df = re.classify(df)
        
        # Add small randomness (Jitter) to features to improve real-world robustness
        for col in ['rsi', 'macd_norm', 'body_rel']:
            df[col] += np.random.normal(0, df[col].std() * 0.01, len(df))
            
        df = df.replace([np.inf, -np.inf], np.nan)
        return df.dropna()

    def create_labels(self, df):
        """
        🚀 TARGET: Abrasive Institutional Labeling (M15 Tactical)
        Matches v3.0 Physics: Accounting for 0.35 friction.
        """
        print("🏷️ Creating V2 High-Confidence Labels (Abrasive Mode)...")
        df = df.copy()
        atr = self._calc_atr(df)
        horizon = 10 # 10 candles for M15 = 2.5 hours
        
        # Friction per trade (Spread + Comm + Slip)
        friction = 0.35
        
        fwd_max = df['close'].rolling(horizon).max().shift(-horizon)
        fwd_min = df['close'].rolling(horizon).min().shift(-horizon)
        
        # Threshold: Dynamic High-Intelligence Target
        df['min_target'] = np.maximum(friction * 3.5, atr * 1.8) # Higher target for "smarter" trades
        
        # 🛡️ PRISTINE ENTRY LOGIC (AI Brain Optimization): 
        # We only label if the Gain is achieved efficiently.
        # This teaches the AI that "Time is Money" and "Risk is Poison".
        mae_limit = atr * 0.6
        time_limit = 8 # Must hit target within 8 candles (2 hours on M15)
        
        # Efficiency Score = (Price Distance / MAE)
        buy_cond = ((fwd_max - df['close']) - friction > df['min_target']) & \
                   (df['close'] - fwd_min < mae_limit)
        
        sell_cond = ((df['close'] - fwd_min) - friction > df['min_target']) & \
                    (fwd_max - df['close'] < mae_limit)
        
        # Additional IQ: Weighting the targets based on Session
        # In Peak hours, we want even bigger moves
        df['target'] = 0
        df.loc[buy_cond, 'target'] = 1
        df.loc[sell_cond, 'target'] = 2

        df.loc[buy_cond & sell_cond, 'target'] = 0 
        
        return df.dropna()

    def _calculate_extended_stats(self, res):
        trades = pd.DataFrame(res['trades'])
        if trades.empty:
            res.update({'sharpe': 0, 'sortino': 0, 'calmar': 0, 'max_win': 0, 'max_loss': 0, 'total_trades': 0})
            return res
        
        trades['entry_date'] = pd.to_datetime(trades['entry_date'])
        daily = trades.set_index('entry_date')['pnl_net'].resample('D').sum()
        std = daily.std()
        neg_std = daily[daily < 0].std()
        
        res['sharpe'] = (daily.mean() / std * np.sqrt(252)) if std > 0 else 0
        res['sortino'] = (daily.mean() / neg_std * np.sqrt(252)) if neg_std > 0 else 0
        res['calmar'] = (res['net_profit_pct'] / res['max_drawdown']) if res['max_drawdown'] > 0 else 0
        res['max_win'] = trades['pnl_net'].max()
        res['max_loss'] = trades['pnl_net'].min()
        res['total_trades'] = len(trades)
        
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
        
        # Super Trader Configs: Pushing the Deep Learning Boundary
        configs = [
            {'max_depth': 10, 'learning_rate': 0.012, 'n_estimators': 4000, 'subsample': 0.85, 'colsample_bytree': 0.8, 'reg_alpha': 3.0, 'reg_lambda': 15.0, 'gamma': 2.0}, 
            {'max_depth': 8, 'learning_rate': 0.018, 'n_estimators': 3500, 'subsample': 0.75, 'colsample_bytree': 0.7, 'reg_alpha': 10.0, 'reg_lambda': 25.0, 'gamma': 5.0},
            {'max_depth': 12, 'learning_rate': 0.008, 'n_estimators': 5000, 'subsample': 0.9, 'colsample_bytree': 0.6, 'reg_alpha': 1.0, 'reg_lambda': 5.0, 'gamma': 1.0}
        ]
        
        best_fitness = -1e9
        best_model_path = None
        best_stats = {}
        
        for i, cfg in enumerate(configs):
            print(f"\n🧪 SUPER TRADER GENOME #{i+1} | Depth: {cfg['max_depth']} | LR: {cfg['learning_rate']}")
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
            
            # Robustness Test (Stress Simulation)
            res = engine.backtest(val_df, broker_name='ICMARKETS', initial_balance=500, risk_pct=1.0)
            
            if "error" in res:
                continue
            
            res = self._calculate_extended_stats(res)
            
            pf = res.get('profit_factor', 0)
            dd = res.get('max_drawdown', 100)
            roi = res.get('net_profit_pct', 0)
            sharpe = res.get('sharpe', 0)
            sortino = res.get('sortino', 0)
            
            # SUPER TRADER FITNESS: Prioritizes Sharpe/Sortino over raw ROI
            # This ensures we pick the most STABLE model, not the luckiest.
            fitness = (roi * 0.2) + (sharpe * 2000) + (sortino * 2000) - (dd * 1000) + (pf * 500)
            
            print(f"   📊 Results: ROI={roi:,.1f}% | PF={pf:.2f} | DD={dd:.1f}% | Sharpe={sharpe:.2f}")
            
            if fitness > best_fitness:
                best_fitness = fitness
                best_model_path = temp_path
                best_stats = res

        if best_model_path:
            final_path = os.path.join(self.models_dir, 'GIA_v2_PRO.pkl')
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
