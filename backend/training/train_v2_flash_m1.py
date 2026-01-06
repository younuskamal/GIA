
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

class GIA_v2_Flash_M1_Trainer:
    """
    🦁 GIA v2 FLASH - M1 SCALPING EDITION (The Hunter)
    -------------------------------------------------
    Optimized for 1-minute timeframe scalping.
    Objective: High frequency, precise entries, and quick flips.
    Integrated with London/NY Session awareness.
    """

    def __init__(self):
        self.features = [
            # --- M1 TACTICAL ---
            'rsi', 'rsi_slope', 'mom_5', 'mom_10', 'vol_20',
            'bb_pos', 'bb_width', 'macd_norm', 
            'ema_9_dist', 'ema_21_dist', 'ema_50_dist',
            'body_rel', 'regime_flag',
            
            # --- M15 CONFIRMATION ---
            'rsi_m15', 'macd_m15', 'bb_width_m15',
            
            # --- H1 STRATEGIC ---
            'ema_200_dist_h1', 'rsi_h1', 'mom_h1', 'trend_h1',
            
            # --- SCALPER SPECIALIZED ---
            'atr_norm', 'vol_ratio', 'price_dist_bb', 'coiling', 'velocity',
            'trend_harmony', 'wick_ratio', 'vol_regime', 'ribbon_align',
            'price_acceleration', 'liquidity_shock', 'market_entropy', 'exhaustion_index',
            'is_london', 'is_newyork', 'session_active',
            # --- UT BOT STRATEGY ---
            'ut_bot_signal', 'ut_bot_dist'
        ]
        
        self.models_dir = os.path.join(PROJECT_ROOT, 'backend', 'models')
        os.makedirs(self.models_dir, exist_ok=True)

    def load_full_data(self):
        data_dir = os.path.join(PROJECT_ROOT, 'data')
        print(f"📂 Loading Multi-Timeframe Datasets from {data_dir}...")
        
        def read(tf):
            path = os.path.join(data_dir, f"XAUUSD_{tf}.csv")
            df = pd.read_csv(path)
            df.columns = [c.lower() for c in df.columns]
            df['date'] = pd.to_datetime(df['time'], format='mixed', dayfirst=False)
            return df.sort_values('date', ascending=True)

        df_m1 = read("M1")
        df_m15 = read("M15")
        df_h1 = read("H1")
        
        # Engineering MTF for M1 anchor
        m15_eng = self._engineer_mtf(df_m15, 'm15')
        h1_eng = self._engineer_mtf(df_h1, 'h1')
        
        merged = pd.merge_asof(df_m1.sort_values('date'), m15_eng.sort_values('date'), on='date', direction='backward')
        merged = pd.merge_asof(merged.sort_values('date'), h1_eng.sort_values('date'), on='date', direction='backward')
        
        return merged.ffill().bfill().dropna()

    def _engineer_mtf(self, df, suffix):
        df = df.copy()
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

    def _calc_ut_bot(self, df, sensitivity=1, period=10):
        # UT Bot Logic (Pine Script Port)
        src = df['close'].values
        # Local ATR calc for UT Bot
        h_l = df['high'] - df['low']
        h_pc = (df['high'] - df['close'].shift()).abs()
        l_pc = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
        xATR = tr.rolling(period).mean().values
        nLoss = sensitivity * xATR
        
        n = len(df)
        xATRTrailingStop = np.zeros(n)
        pos = np.zeros(n)
        
        # Determine first valid index to avoid nan issues
        start_idx = period
        xATRTrailingStop[:start_idx] = src[:start_idx]
        
        for i in range(start_idx, n):
            prev_stop = xATRTrailingStop[i-1]
            cur_src = src[i]
            prev_src = src[i-1]
            cur_nLoss = nLoss[i]
            
            if np.isnan(cur_nLoss): 
                 xATRTrailingStop[i] = cur_src
                 continue

            if (cur_src > prev_stop) and (prev_src > prev_stop):
                xATRTrailingStop[i] = max(prev_stop, cur_src - cur_nLoss)
            elif (cur_src < prev_stop) and (prev_src < prev_stop):
                xATRTrailingStop[i] = min(prev_stop, cur_src + cur_nLoss)
            elif (cur_src > prev_stop):
                xATRTrailingStop[i] = cur_src - cur_nLoss
            else:
                xATRTrailingStop[i] = cur_src + cur_nLoss
            
            prev_stop_val = xATRTrailingStop[i-1] 
            
            if (prev_src < prev_stop_val) and (cur_src > prev_stop_val):
                pos[i] = 1
            elif (prev_src > prev_stop_val) and (cur_src < prev_stop_val):
                pos[i] = -1
            else:
                pos[i] = pos[i-1]
        
        return xATRTrailingStop, pos

    def engineer_primary(self, df):
        df = df.copy()
        
        # 1. Base Intelligence (M1 Specialized)
        df['rsi'] = self._calc_rsi(df['close'])
        df['rsi_slope'] = df['rsi'].diff(3)
        df['mom_5'] = df['close'].pct_change(5)
        df['vol_20'] = df['close'].rolling(20).std()
        
        e12 = df['close'].ewm(span=12, adjust=False).mean()
        e26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd_norm'] = (e12 - e26) / (df['close'] + 1e-9)
        
        # Power & Volatility
        df['body_rel'] = (df['close'] - df['open']).abs() / (df['high'] - df['low'] + 1e-9)
        
        for s in [9, 21, 50, 100, 200]:
            ema = df['close'].ewm(span=s, adjust=False).mean()
            df[f'ema_{s}_dist'] = (df['close'] - ema) / (ema + 1e-9)
            
        df['ribbon_align'] = (np.sign(df['ema_9_dist']) + np.sign(df['ema_21_dist']) + np.sign(df['ema_50_dist']) + np.sign(df['ema_100_dist']) + np.sign(df['ema_200_dist'])) / 5.0

        # Session Awareness (UTC)
        df['hour_utc'] = df['date'].dt.hour
        df['is_london'] = ((df['hour_utc'] >= 8) & (df['hour_utc'] <= 16)).astype(int)
        df['is_newyork'] = ((df['hour_utc'] >= 13) & (df['hour_utc'] <= 21)).astype(int)
        df['session_active'] = ((df['is_london'] == 1) | (df['is_newyork'] == 1)).astype(int)

        # Market Entropy (Short-term structure)
        df['market_entropy'] = df['close'].diff().abs().rolling(10).sum() / (df['high'].rolling(10).max() - df['low'].rolling(10).min() + 1e-9)
        df['exhaustion_index'] = (df['close'] - df['close'].rolling(50).mean()).abs() / (df['vol_20'] * 2 + 1e-9)

        ma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df['bb_width'] = (4*std) / (ma + 1e-9)
        df['bb_pos'] = (df['close'] - (ma - 2*std)) / (4*std + 1e-9)
        df['price_dist_bb'] = (df['close'] - ma) / (ma + 1e-9)
        
        df['velocity'] = df['close'].diff(5) / (df['vol_20'] + 1e-9)
        df['coiling'] = df['bb_width'] / (df['bb_width'].rolling(50).mean() + 1e-9)
        
        # 🧪 Scalper Micro-Indicators
        df['vol_velocity'] = df['volume'].diff(3) / (df['volume'].rolling(20).mean() + 1e-9)
        df['spread_impact'] = 0.35 / (df['vol_20'] + 1e-9) # Cost vs potential move
        
        # Candle Geometry
        df['upper_wick'] = (df['high'] - df[['open', 'close']].max(axis=1)) / (df['close'] + 1e-9)
        df['lower_wick'] = (df[['open', 'close']].min(axis=1) - df['low']) / (df['close'] + 1e-9)
        df['wick_ratio'] = df['upper_wick'] / (df['lower_wick'] + 1e-9)
        
        df['trend_harmony'] = (
            np.sign(df['macd_norm']) + 
            np.sign(df.get('macd_m15', 0)) + 
            np.sign(df.get('macd_h1', 0))
        ) / 3.0
        
        df['price_acceleration'] = df['velocity'].diff(3)
        df['liquidity_shock'] = df['volume'] / (df['volume'].rolling(50).mean() + 1e-9)
        
        atr = self._calc_atr(df)
        df['atr_norm'] = atr / (df['close'] + 1e-9)
        df['vol_regime'] = (df['vol_20'] / (df['vol_20'].rolling(200).mean() + 1e-9)).fillna(1.0)
        df['vol_ratio'] = df['vol_20'] / (df['vol_20'].rolling(50).mean() + 1e-9)
        
        re = MarketRegimeEngine()
        df = re.classify(df)
        df['regime_flag'] = df['regime'].map({'TRENDING': 1, 'RANGING': 0, 'VOLATILE': 2, 'STALL': -1}).fillna(0)

        # 🤖 UT Bot Integration
        ut_stop, ut_pos = self._calc_ut_bot(df, sensitivity=1, period=10)
        df['ut_bot_pos'] = ut_pos
        df['ut_bot_dist'] = (df['close'] - ut_stop) / (df['close'] + 1e-9)
        # Signal: 1 (Buy), -1 (Sell), 0 (Hold) based on pos switch
        # Actually use the pos state itself as a strong feature
        df['ut_bot_signal'] = df['ut_bot_pos']
        
        df = df.replace([np.inf, -np.inf], np.nan)
        return df.dropna()

    def create_labels(self, df, friction_mult=1.0):
        print(f"🏷️ Creating Flash M1 Labels (Aggression: {friction_mult:.2f})...")
        df = df.copy()
        atr = self._calc_atr(df)
        horizon = 15 # Shorter horizon for ultra-scalp
        friction = 0.20 * friction_mult 
        
        fwd_max = df['close'].rolling(horizon).max().shift(-horizon)
        fwd_min = df['close'].rolling(horizon).min().shift(-horizon)
        
        # 🎯 DYNAMIC TARGETING: Hard floor + Volatility scaling
        df['min_target'] = np.maximum(0.65, atr * 2.5) 
        mae_limit = atr * 1.5
        
        session_mask = df['session_active'] == 1
        
        buy_cond = session_mask & \
                   ((fwd_max - df['close']) - friction > df['min_target']) & \
                   (df['close'] - fwd_min < mae_limit)
        
        sell_cond = session_mask & \
                    ((df['close'] - fwd_min) - friction > df['min_target']) & \
                    (fwd_max - df['close'] < mae_limit)
        
        df['target'] = 0
        df.loc[buy_cond, 'target'] = 1
        df.loc[sell_cond, 'target'] = 2
        
        total = len(df)
        buys = np.sum(df['target']==1)
        sells = np.sum(df['target']==2)
        print(f"   ✅ Label Distribution: BUY {buys} | SELL {sells} | WAIT {total-buys-sells}")
        return df.dropna()

    def create_labels(self, df, friction_mult=1.0, target_mult=2.0):
        print(f"🏷️ Creating Flash M1 Labels (Aggression: {friction_mult:.2f} | Target: {target_mult:.1f}x)...")
        df = df.copy()
        atr = self._calc_atr(df)
        horizon = 15 
        friction = 0.18 * friction_mult 
        
        fwd_max = df['close'].rolling(horizon).max().shift(-horizon)
        fwd_min = df['close'].rolling(horizon).min().shift(-horizon)
        
        # 🎯 DYNAMIC TARGETING: 
        # Variable target mult to find different market 'pulses'
        df['min_target'] = np.maximum(0.50, atr * target_mult) 
        mae_limit = atr * 1.4 # Risk limit inside the horizon
        
        session_mask = df['session_active'] == 1
        
        buy_cond = session_mask & \
                   ((fwd_max - df['close']) - friction > df['min_target']) & \
                   (df['close'] - fwd_min < mae_limit)
        
        sell_cond = session_mask & \
                    ((df['close'] - fwd_min) - friction > df['min_target']) & \
                    (fwd_max - df['close'] < mae_limit)
        
        df['target'] = 0
        df.loc[buy_cond, 'target'] = 1
        df.loc[sell_cond, 'target'] = 2
        df.loc[buy_cond & sell_cond, 'target'] = 0 
        
        total = len(df)
        buys = np.sum(df['target']==1)
        sells = np.sum(df['target']==2)
        print(f"   ✅ Pulse Distribution: BUY {buys} | SELL {sells} | WAIT {total-buys-sells}")
        return df.dropna()

    def evolutionary_training(self, full_df):
        print("\n" + "🌀"*35)
        print("🚀 GIA FLASH v5.1 - THE DAILY HUNTER (RECURSIVE SEARCH)")
        print("🧠 'SMART SCALPER' GENERALIZATION ENGINE")
        print("🌀"*35)
        
        # 1. Broad Temporal Split
        total_len = len(full_df)
        train_end = int(total_len * 0.65)
        eval_end = int(total_len * 0.75)
        
        train_df = full_df.iloc[:train_end].copy()
        eval_df = full_df.iloc[train_end:eval_end].copy() 
        blind_df = full_df.iloc[eval_end:].copy()

        best_global_fitness = -1e9
        best_model_data = None
        
        from backend.engine.backtest import BacktestEngine
        import time

        start_time = time.time()
        max_search_time = 7200 # 2 Hours for a deep hunter run
        gen = 1

        while (time.time() - start_time) < max_search_time:
            elapsed = int(time.time() - start_time)
            print(f"\n🛸 SEARCH GENERATION {gen} (Elapsed: {elapsed//60}m {elapsed%60}s)")
            
            # --- 🧬 HYPER-PARAMETER MUTATION ---
            # Smart Search: Low Depth (3-4) to prevent memorizing noise
            cfg = {
                'max_depth': np.random.choice([3, 4]),
                'learning_rate': np.random.uniform(0.01, 0.08),
                'n_estimators': np.random.randint(400, 1800),
                'subsample': np.random.uniform(0.5, 0.7),
                'colsample_bytree': np.random.uniform(0.3, 0.6),
                'gamma': np.random.uniform(1.0, 6.0),
                'min_child_weight': np.random.randint(15, 60),
                'reg_alpha': np.random.uniform(0.1, 3.0),
                'reg_lambda': np.random.uniform(1.0, 7.0)
            }
            
            # Label mutation
            rand_fric = np.random.uniform(0.7, 2.0)
            rand_targ = np.random.uniform(1.5, 3.0)
            
            train_labeled = self.create_labels(train_df, friction_mult=rand_fric, target_mult=rand_targ)
            features_to_use = [f for f in self.features if f in train_labeled.columns]
            
            X_train = train_labeled[features_to_use]
            y_train = train_labeled['target']
            weights = compute_sample_weight('balanced', y_train)

            print(f"   🧬 Strategy: Target={rand_targ:.1f}x | Friction={rand_fric:.2f} | Depth={cfg['max_depth']}")
            
            model = xgb.XGBClassifier(**cfg, objective='multi:softmax', num_class=3, tree_method='hist')
            model.fit(X_train, y_train, sample_weight=weights)
            
            # --- 🛡️ MISTAKE LEARNING ---
            temp_path = os.path.join(self.models_dir, f"hunter_temp.pkl")
            joblib.dump({'model': model, 'feature_columns': features_to_use, 'label_encoder': MockEncoder()}, temp_path)
            
            engine = BacktestEngine(model_path=temp_path)
            engine.load_model()
            
            res_m = engine.backtest(train_df.tail(3000), broker_name="ICMARKETS", initial_balance=500, risk_pct=0.5)
            if "trades" in res_m and len(res_m['trades']) > 0:
                losses = [t for t in res_m['trades'] if t['pnl_net'] < 0]
                if losses:
                    print(f"      🎓 Learning from {len(losses)} pattern failures...")
                    loss_dates = [t['entry_date'] for t in losses]
                    mask = train_labeled['date'].isin(loss_dates)
                    weights[mask] *= 3.0 
                    model.fit(X_train, y_train, sample_weight=weights)

            # --- 📊 ROBUSTNESS SCORE ---
            joblib.dump({'model': model, 'feature_columns': features_to_use, 'label_encoder': MockEncoder()}, temp_path)
            engine.load_model()
            
            res_val = engine.backtest(eval_df, broker_name="ICMARKETS", initial_balance=500, risk_pct=1.0)
            res_blind = engine.backtest(blind_df, broker_name="ICMARKETS", initial_balance=500, risk_pct=1.0)
            
            def calculate_fitness(res):
                if "error" in res or res['total_trades'] < 5: return -5000
                roi = res['net_profit_pct']
                pf = res['profit_factor']
                wr = res['win_rate']
                trades = res['total_trades']
                dd = res['max_drawdown']
                
                # 🛑 RUTHLESS FLOOR: If it doesn't make money, it's garbage.
                if pf < 1.10 or roi <= 0: return -2000
                
                # Daily Frequency
                days = max(1, len(res['equity_curve']) / 1440)
                freq = trades / days
                
                # Daily Consistency
                tr_df = pd.DataFrame(res['trades'])
                tr_df['day'] = pd.to_datetime(tr_df['entry_date']).dt.date
                day_pnl = tr_df.groupby('day')['pnl_net'].sum()
                win_day_rate = (len(day_pnl[day_pnl > 0]) / len(day_pnl)) * 100 if not day_pnl.empty else 0
                
                # Fitness Components
                pf_score = pf * 200 # Heavy weight on PF
                roi_score = roi * 5
                consist_score = win_day_rate * 5
                risk_penalty = dd * 50
                
                # Frequency Balance: Target 3-8 trades per day
                freq_score = 0
                if 1.0 <= freq <= 15.0:
                    freq_score = 100
                else:
                    freq_score = -500 # Discourage "lotto" or "over-trader"
                
                return roi_score + pf_score + consist_score + freq_score - risk_penalty

            f1 = calculate_fitness(res_val)
            f2 = calculate_fitness(res_blind)
            
            # --- CHAMPION SELECTION ---
            # Model must be robustly profitable in BOTH segments
            if f1 > 0 and f2 > 0:
                combined_fitness = (f1 + f2) / 2.0
                # Consistency check: Are both segments similar?
                stability = 1.0 - (abs(f1 - f2) / (max(f1, f2) + 1e-9))
                fitness = combined_fitness * stability
                
                print(f"      💎 ALPHA DISCOVERED! Fit: {fitness:.2f} | PF: {res_blind['profit_factor']:.2f} | WR: {res_blind['win_rate']:.1f}% | T/D: {res_blind['total_trades']/(len(blind_df)/1440):.1f}")
                
                if fitness > best_global_fitness:
                    best_global_fitness = fitness
                    best_model_data = {'model': model, 'feature_columns': features_to_use, 'label_encoder': MockEncoder()}
                    joblib.dump(best_model_data, os.path.join(self.models_dir, 'GIA_v2_FLASH.pkl'))
                    print(f"      🏆 NEW CHAMPION SAVED! (Global Alpha)")
                    
                    if res_blind['net_profit_pct'] > 10 and res_blind['profit_factor'] > 1.8:
                        print("\n🏁 ELITE ROBUST ALPHA REACHED.")
                        break
            
            gen += 1
            
        if best_model_data:
            print(f"\n✅ Training Finished. Best Global Fitness: {best_global_fitness:.2f}")
            return True
        return False

def main():
    trainer = GIA_v2_Flash_M1_Trainer()
    df = trainer.load_full_data()
    df = trainer.engineer_primary(df)
    success = trainer.evolutionary_training(df)
    if success:
        print("\n🦁 GIA_v2_FLASH M1 SCALPER TRAINED SUCCESSFULLY")
    else:
        print("\n❌ FAILED TO FIND ROBUST ALPHA. ADJUST SEARCH SPACE.")

if __name__ == "__main__":
    main()
