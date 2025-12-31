
import os
import sys
import pandas as pd
import numpy as np
import joblib
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from backend.engine.backtest import BacktestEngine
from GIA_SIGNAL_PRO.core.trainer import GIA_Apex_Distiller
from GIA_SIGNAL_PRO.config.settings import MODEL_PATH

def run_signal_pro_backtest():
    print("🦁 Starting GIA SIGNAL PRO Backtest (Inside Backend Context)")
    print("-" * 50)
    
    # 1. Load Model Data
    if not os.path.exists(MODEL_PATH):
        print(f"❌ Model not found at {MODEL_PATH}")
        return

    # 2. Data Preparation
    distiller = GIA_Apex_Distiller()
    df1, df5, df15, dfh1 = distiller.load_data()
    
    print("🛠️ Engineering features for backtest...")
    df = distiller.engineer_features(df1, df5, df15, dfh1)
    
    # Filter for backtest period
    bt_df = df[df['date'].dt.year >= 2023].copy()
    if bt_df.empty:
        print("⚠️ No data found for 2023+, using last 20000 bars.")
        bt_df = df.tail(20000).copy()
    else:
        print(f"✅ Found {len(bt_df)} bars from 2023-2025.")

    # 3. Model Inference (Pre-calculating signals for the engine)
    print("🧠 Generating model signals...")
    model_data = joblib.load(MODEL_PATH)
    model = model_data['model']
    calibrator = model_data['calibrator']
    features = model_data['features']
    
    X = bt_df[features]
    raw_probs = model.predict_proba(X)
    calibrated_probs = calibrator.calibrate(raw_probs)
    
    # Format signals for BacktestEngine
    # The engine expects 'y_pred_labels' and 'y_pred_probs' if passed via external_signals
    pred_idx = np.argmax(calibrated_probs, axis=1)
    labels = []
    for idx in pred_idx:
        if idx == 0: labels.append('WAIT')
        elif idx == 1: labels.append('BUY')
        else: labels.append('SELL')
        
    probs = np.max(calibrated_probs, axis=1)
    
    external_signals = {
        'labels': labels,
        'probs': probs
    }

    # 4. Initialize Core Backtest Engine
    # We pass None for model_path because we provide external_signals
    engine = BacktestEngine(model_path=None) 
    
    print(f"🚀 Simulation starting on {len(bt_df)} bars...")
    results = engine.backtest(
        df=bt_df,
        initial_balance=10000,
        risk_pct=0.5,
        sizing_mode='dynamic',
        external_signals=external_signals
    )

    # 5. Output Results
    if "error" in results:
        print(f"❌ Backtest Failed: {results['error']}")
        if "diagnostic" in results:
            print(f"Details: {results['diagnostic']}")
        return

    print("\n" + "📈"*10 + " BACKTEST RESULTS " + "📈"*10)
    print(f"Net Profit: ${results['net_profit']:.2f} ({results['net_profit_pct']:.2f}%)")
    print(f"Win Rate: {results['win_rate']:.2f}%")
    print(f"Profit Factor: {results['profit_factor']:.2f}")
    print(f"Max Drawdown: {results['max_drawdown']:.2f}%")
    print(f"Total Trades: {results['total_trades']}")
    print("📈" * 25)

if __name__ == "__main__":
    run_signal_pro_backtest()
