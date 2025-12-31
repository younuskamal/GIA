import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
import joblib
import xgboost as xgb

# Fix path for package imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from backend.data.loaders import load_history_data
from backend.data.processor import process_raw_data
from backend.training.train_xgb import GoldModelTrainer
from backend.engine.backtest import BacktestEngine
from backend.core.rules import SystemMode

def train_v1_1_evolution():
    """
    🦁 GIA v1.1 OMNI-TRAINER
    Strategy: Unified intelligence from M1, M15, M30, and H1.
    Goal: Beat v14 PRO by understanding every scale of market movement.
    """
    print("="*75)
    print("🦁 GIA OMNI-EVOLUTION: [M1 + M15 + M30 + H1] -> v1.1 PRO")
    print("="*75)
    
    timeframes = ['M1', 'M15', 'M30', 'H1'] # Full Omni-Scale
    all_dfs = []

    # 1. Load and Process Every Scale
    for tf in timeframes:
        print(f"📂 Loading and Engineering {tf} Scale...")
        df_raw = load_history_data(timeframe=tf, start_year=2018, end_year=2023)
        if df_raw is None or len(df_raw) < 2100: # Need at least 2016 for monthly momentum
            print(f"   ⚠️ Skipping {tf}: Insufficient history for indicators.")
            continue
        
        df_p = process_raw_data(df_raw)
        if df_p is None or df_p.empty:
            print(f"   ⚠️ Skipping {tf}: Feature engineering failed/empty.")
            continue
        
        # --- SYNTHETIC NEWS ENRICHMENT (Fixed Alignment) ---
        shock_threshold = df_p['rel_range'].quantile(0.98)
        mask = df_p['rel_range'] > shock_threshold
        df_p.loc[mask, 'news_impact_score'] = 3
        df_p.loc[mask, 'news_sentiment'] = np.where(df_p.loc[mask, 'close'] > df_p.loc[mask, 'open'], 1, -1)
        
        # --- ELITE LABELING (Contextual Scale Adjustment) ---
        if tf == 'M1': horizon, threshold = 60, 0.12 # Scalping (1 hour window)
        elif tf == 'M15': horizon, threshold = 8, 0.25
        else: horizon, threshold = 4, 0.40 # Swing
        
        df_p['max_future_ret'] = df_p['close'].rolling(window=horizon).max().shift(-horizon) / df_p['close'] - 1
        df_p['min_future_ret'] = df_p['close'].rolling(window=horizon).min().shift(-horizon) / df_p['close'] - 1
        
        df_p['label'] = 'WAIT'
        df_p.loc[df_p['max_future_ret'] > (threshold/100), 'label'] = 'BUY'
        df_p.loc[df_p['min_future_ret'] < -(threshold/100), 'label'] = 'SELL'
        
        df_p = df_p.dropna().reset_index(drop=True)
        all_dfs.append(df_p)

    if not all_dfs:
        print("❌ FAILED: No data sources found.")
        return

    # Combine into Super-Dataset
    full_dataset = pd.concat(all_dfs).sort_values('date').reset_index(drop=True)
    full_dataset['date'] = pd.to_datetime(full_dataset['date'])
    
    # 2. Split
    train_df = full_dataset[full_dataset['date'] < '2023-01-01'].copy()
    val_df = full_dataset[(full_dataset['date'] >= '2023-01-01') & (full_dataset['date'] < '2024-01-01')].copy()
    
    print(f"📊 OMNI Samples: {len(train_df):,} | Val Samples: {len(val_df):,}")

    # All 29+ Features (including Sessions)
    v14_features = [
        'rsi', 'rsi_slope', 'ema_9_dist', 'ema_21_dist', 'ema_50_dist', 
        'atr_pct', 'rel_range', 'bb_width', 'macd_norm', 'bb_pos', 'stoch_k', 
        'body_size', 'upper_wick', 'lower_wick', 'mom_weekly', 'mom_monthly',
        'ret_1', 'ret_2', 'ret_3', 'vol_5', 'vol_20', 'mom_3', 'mom_5', 'mom_10',
        'is_london', 'is_ny', 'is_asian', 'news_sentiment', 'news_impact_score'
    ]

    # 3. Evolutionary Search (Omni-Scale Selection)
    search_space = [
        {'max_depth': 8,  'learning_rate': 0.01,  'n_estimators': 2500, 'booster': 'dart'}, 
        {'max_depth': 10, 'learning_rate': 0.005, 'n_estimators': 4000, 'colsample_bytree': 0.7},
        {'max_depth': 7,  'learning_rate': 0.02,  'n_estimators': 2000, 'subsample': 0.8},
        {'max_depth': 12, 'learning_rate': 0.003, 'n_estimators': 5000, 'colsample_bytree': 0.6},
    ]
    
    best_candidate = None
    best_fitness = -9999
    models_dir = os.path.join(PROJECT_ROOT, 'backend', 'models')

    from sklearn.utils.class_weight import compute_sample_weight

    for i, params in enumerate(search_space):
        print(f"\n🚀 Generation {i+1}: {params}")
        trainer = GoldModelTrainer()
        trainer.feature_columns = v14_features
        trainer.model_params.update(params)
        
        X_t, y_t, _ = trainer.prepare_features(train_df)
        weights = compute_sample_weight('balanced', y_t)
        
        trainer.model = xgb.XGBClassifier(**trainer.model_params)
        trainer.model.fit(X_t, y_t, sample_weight=weights)
        
        temp_path = os.path.join(models_dir, 'GIA_v1.1_SEARCH.pkl')
        trainer.save_model(temp_path)
        
        # --- STRESS TEST VALIDATION ---
        # Using STRESS_TEST broker ($10 commission, high spread)
        # This ensures the model is profitable under worst-case conditions.
        engine = BacktestEngine(model_path=temp_path)
        engine.load_model()
        res = engine.backtest(val_df[val_df['atr_pct'] > 0], broker_name='STRESS_TEST', risk_pct=0.5)
        
        ret = res.get('total_return_pct', 0)
        dd = res.get('max_drawdown_pct', 0)
        pf = res.get('profit_factor', 0)
        # Fitness Score: Return - (2.0 * Drawdown) + pf bonus
        fitness = ret - (2.0 * dd) + (pf * 5)
        
        print(f"      📈 STRESS RESULTS: Ret: {ret:.1f}% | DD: {dd:.1f}% | PF: {pf:.2f} | Fitness: {fitness:.2f}")
        
        if fitness > best_fitness:
            best_fitness = fitness
            best_candidate = trainer
            print(f"      🌟 STRESS-MASTER CANDIDATE NOMINATED!")

    # 4. Finalize
    if best_candidate and best_fitness > 0:
        print(f"\n💎 Finalizing GIA_v1.1_PRO.pkl (The Omni-Master)...")
        X_full, y_full, _ = best_candidate.prepare_features(full_dataset)
        weights_full = compute_sample_weight('balanced', y_full)
        best_candidate.model.fit(X_full, y_full, sample_weight=weights_full)
        
        final_path = os.path.join(models_dir, 'GIA_v1.1_PRO.pkl')
        best_candidate.save_model(final_path)
        print(f"✅ SUCCESS: GIA_v1.1_PRO.pkl is now the most advanced model.")
    else:
        print("\n❌ FAILED: Performance too low for promotion.")

    print(f"\n👉 Compare GIA_v14_PRO.pkl vs GIA_v1.1_PRO.pkl on 2024+ data.")

    print(f"\n👉 Next Step: Run backtest comparison.")

    print(f"\n👉 Next Step: Run backtests via run_backtest.py for OOS Validation.")

if __name__ == "__main__":
    train_v1_1_evolution()
