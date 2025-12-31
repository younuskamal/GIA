"""
Master Intelligence Pipeline - Professional Evolutionary Engine
V4.0 - Hybrid Deep Learning & Gradient Boosting
"""
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

# Fix path for package imports
BASE_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_BACKEND not in sys.path:
    sys.path.append(BASE_BACKEND)

from core.registry import ModelManager
from data.processor import build_professional_dataset
from training.train_xgb import GoldModelTrainer
from training.train_lstm import GoldLSTMTrainer
from engine.backtest import BacktestEngine

def run_pro_pipeline():
    """
    Evolves the model through multiple generations of intelligence.
    Learns from financial mistakes by iteratively searching for robust strategies.
    """
    manager = ModelManager()
    ROOT_DIR = Path(__file__).parent.parent
    dataset_path = ROOT_DIR / 'gold_dataset_pro.csv'
    candidate_model_path = ROOT_DIR / 'candidate_model.pkl'

    print("\n" + "🔥"*10 + " GIA EVOLUTIONARY ENGINE START " + "🔥"*10)
    
    # 1. Refresh Data
    dataset = build_professional_dataset(period="max")
    if dataset is None: return False
    dataset.to_csv(dataset_path, index=False)

    # 2. Competitive Multi-Arch Training
    # We test different "Personalities" of models
    strategies = [
        # The 'GrandMaster' Model (High Depth for High Precision Labels)
        {'type': 'XGB', 'max_depth': 8, 'learning_rate': 0.01, 'n_estimators': 2000, 'label': 'GrandMaster'},
        # The 'SafetyFirst' Model (High Regularization)
        {'type': 'XGB', 'max_depth': 3, 'learning_rate': 0.05, 'n_estimators': 800, 'reg_alpha': 1.0, 'colsample_bytree': 0.6, 'label': 'SafetyFirst'},
    ]

    best_score = -9999
    winner_metrics = None

    for attempt, params in enumerate(strategies, 1):
        s_label = params.pop('label')
        s_type = params.pop('type')
        print(f"\n🚀 GENERATION #{attempt} | Strategy: {s_label} ({s_type})")
        
        try:
            if s_type == 'XGB':
                trainer = GoldModelTrainer(dataset_path=str(dataset_path))
                df = trainer.load_data()
                X, y, _ = trainer.prepare_features(df)
                Xt, Xts, Xv, yt, yts, yv = trainer.split_data(X, y)
                trainer.model_params.update(params)
                trainer.train_model(Xt, yt, Xv, yv)
                eval_res = trainer.evaluate(Xt, yt, Xts, yts)
            else:
                trainer = GoldLSTMTrainer(window_size=params['window_size'])
                df = pd.read_csv(dataset_path)
                X_seq, y_seq = trainer.prepare_sequences(df)
                n = len(X_seq)
                train_end, val_end = int(n*0.7), int(n*0.85)
                trainer.build_model(input_shape=(trainer.window_size, X_seq.shape[2]))
                history = trainer.train(X_seq[:train_end], y_seq[:train_end], 
                                      X_seq[train_end:val_end], y_seq[train_end:val_end], 
                                      epochs=params['epochs'])
                gap = abs(history.history['accuracy'][-1] - history.history['val_accuracy'][-1])
                # Relaxed bias gap for LSTM to 25%
                eval_res = {'is_biased': gap > 0.25, 'bias_gap': gap, 'accuracy': history.history['accuracy'][-1]}

            if eval_res['is_biased']:
                print(f"   ❌ REJECTED: Unstable/Biased (Gap: {eval_res['bias_gap']*100:.1f}%)")
                continue

            # Financial Validation
            trainer.save_model(path=str(candidate_model_path))
            engine = BacktestEngine(model_path=str(candidate_model_path), dataset_path=str(dataset_path))
            engine.load_model()
            
            # GIA v1.10 Strict Validation
            # We must use STRATEGY_TEST_MODE to ensure the model survives the exact production rules
            # (Stops, Cooldowns, Equity Halt)
            from backend.core.rules import SystemMode
            
            print(f"      📊 Validating with Professional Strategy Rules...")
            bt = engine.backtest(df, initial_balance=1000, lot_size=0.1, mode=SystemMode.STRATEGY_TEST_MODE) # lot_size ignored in this mode
            
            # Fitness Score: Return - (1.5 * Drawdown)
            fitness = bt['total_return_pct'] - (1.5 * bt['max_drawdown_pct'])
            
            # Fitness Score: Return - (1.5 * Drawdown)
            fitness = bt['total_return_pct'] - (1.5 * bt['max_drawdown_pct'])
            
            # We delegate final approval to the Registry, but we must filter out absolute disasters here.
            # If it survived without Margin Call, it's a candidate.
            if not bt['margin_called']:
                if fitness > best_score:
                    best_score = fitness
                    winner_metrics = {
                        "accuracy": bt['overall_accuracy'],
                        "max_drawdown": bt['max_drawdown_pct'],
                        "total_return_pct": bt['total_return_pct'],
                        "trades": bt['simulated_trades'],
                        "fitness": fitness
                    }
                    winner_path = str(candidate_model_path) # Keep track of best file
                    print(f"      🌟 CANDIDATE NOMINATED! Fitness: {fitness:.2f} (Return: {bt['total_return_pct']:.1f}%)")
            else:
                print(f"      ⚠️ Crashed (Margin Call).")

        except Exception as e:
            print(f"   ⚠️ Generation failed: {e}")

    if winner_metrics:
        print(f"\n📢 Submitting Best Candidate to Registry... (Return: {winner_metrics['total_return_pct']:.1f}%)")
        # Registry will decide if it beats the current active model
        is_approved, reason = manager.register_candidate(winner_path, winner_metrics)
        if is_approved:
            print(f"🏆 APPROVED! {reason}")
            return True
        else:
            print(f"❌ REJECTED by Registry: {reason}")
            return False
    
    print("\n❌ No models survived the evolution. Retaining current intelligence.")
    return False

if __name__ == "__main__":
    run_pro_pipeline()
