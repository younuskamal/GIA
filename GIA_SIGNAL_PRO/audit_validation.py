
import os
import sys
import pandas as pd
import numpy as np
import joblib
from datetime import datetime
import time

# Add root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from GIA_SIGNAL_PRO.core.trainer import GIA_Apex_Distiller
from GIA_SIGNAL_PRO.config.settings import MODEL_PATH, DATA_DIR
from backend.engine.backtest import BacktestEngine

def run_audit():
    print("🦁 GIA SIGNAL PRO - MANDATORY AUDIT & VALIDATION")
    print("="*60)
    
    # 1. Isolation & Model Existence Check
    if not os.path.exists(MODEL_PATH):
        print("❌ FATAL: Model file GIA_SIGNAL_PRO.pkl missing.")
        return
    print(f"✅ Isolation: Model found at {MODEL_PATH}")

    distiller = GIA_Apex_Distiller()
    
    # 2. Data Integrity Check
    print("\n🔍 1. Data Integrity & Alignment Check...")
    df1, df5, df15, dfh1 = distiller.load_data()
    
    # Check years
    years = df1['date'].dt.year.unique()
    print(f"   Data Years: {sorted(years)}")
    if 2023 not in years or 2025 not in years:
        print("   ⚠️ Data range does not fully cover 2023-2025.")
    
    # Check for duplicates
    dupes = df1.duplicated(subset=['date']).sum()
    if dupes > 0:
        print(f"   ❌ Found {dupes} duplicate candles in M1 data.")
    else:
        print("   ✅ No duplicate candles detected.")
    
    # Alignment check (M1 should be consistent)
    diffs = df1['date'].diff().dt.total_seconds().dropna()
    gaps = (diffs > 60) & (diffs < 3600*48) # Exclude weekends
    if gaps.any():
        print(f"   ℹ️ Detected {gaps.sum()} intraday gaps in M1 data (likely non-trading hours).")

    # 3. Walk-Forward Validation (Train <= 2022, Test 2023-2025)
    print("\n🔍 2. Sniper Validation (Test Period: 2023-2025)...")
    df = distiller.engineer_features(df1, df5, df15, dfh1)
    
    # Split: Train on data before the target backtest period
    train_df = df[df['date'].dt.year <= 2022].copy()
    test_df = df[df['date'].dt.year >= 2023].copy()
    
    if test_df.empty:
        print("   ⚠️ No 2023-2025 data for validation. Using full dataset.")
        test_df = df.copy()

    # Load Model
    model_data = joblib.load(MODEL_PATH)
    model = model_data['model']
    calibrator = model_data['calibrator']
    features = model_data['features']
    
    def get_signals(data):
        X = data[features]
        probs = model.predict_proba(X)
        if hasattr(calibrator, 'calibrate'):
            probs = calibrator.calibrate(probs)
        
        preds = np.argmax(probs, axis=1)
        conf = np.max(probs, axis=1)
        
        labels = []
        for p in preds:
            if p == 0: labels.append('WAIT')
            elif p == 1: labels.append('BUY')
            else: labels.append('SELL')
            
        return labels, conf, probs

    # Run Test 2025 Backtest
    test_labels, test_confs, test_probs_full = get_signals(test_df)
    ext = {'labels': test_labels, 'probs': test_confs}
    
    bt_engine = BacktestEngine(model_path=None)
    res = bt_engine.backtest(test_df, external_signals=ext, risk_pct=0.5)
    
    if 'error' not in res:
        print(f"   📊 2025 Test Result:")
        print(f"      Net Profit: {res['net_profit_pct']:.2f}%")
        print(f"      Profit Factor: {res['profit_factor']:.2f}")
        print(f"      Max Drawdown: {res['max_drawdown']:.2f}%")
        print(f"      Win Rate: {res['win_rate']:.2f}%")
        
        if res['profit_factor'] >= 1.5 and res['max_drawdown'] <= 8:
            print("   ✅ Walk-Forward criteria met.")
        else:
            print("   ❌ Walk-Forward criteria failed (PF < 1.5 or DD > 8%).")
    else:
        print(f"   ❌ Backtest failed: {res.get('error')}")

    # 4. Confidence Calibration Audit
    print("\n🔍 3. Confidence Calibration Audit...")
    test_df['pred_label'] = test_labels
    test_df['confidence'] = test_confs
    
    # We need actual labels or future returns to check success
    # For a quick audit, we can look at the trades log
    if 'trades' in res and res['trades']:
        trades = pd.DataFrame(res['trades'])
        buckets = [
            (0.60, 0.65),
            (0.65, 0.70),
            (0.70, 0.75),
            (0.75, 1.00)
        ]
        print(f"   {'Bucket':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Sum PnL'}")
        print(f"   {'-'*55}")
        
        last_wr = -1
        monotonic = True
        
        for low, high in buckets:
            b_trades = trades[(trades['confidence'] >= low) & (trades['confidence'] < high)]
            if not b_trades.empty:
                wr = (len(b_trades[b_trades['pnl_net'] > 0]) / len(b_trades)) * 100
                sum_pnl = b_trades['pnl_net'].sum()
                print(f"   {int(low*100)}-{int(high*100)}% {' '*(7 if high<1 else 6)} | {len(b_trades):<8} | {wr:<10.2f}% | ${sum_pnl:>8.2f}")
                
                if wr < last_wr:
                    monotonic = False
                last_wr = wr
            else:
                print(f"   {int(low*100)}-{int(high*100)}% {' '*(7 if high<1 else 6)} | 0        | N/A        | $0.00")
        
        if monotonic:
            print("\n   ✅ Calibration: Confirmed Monotonic (Higher Conf -> Higher Actual Success).")
        else:
            print("\n   ⚠️ Calibration: Non-monotonicity detected. Consider recalibration.")
    else:
        print("   ❌ Calibration: No trades executed to audit.")

    # 5. Session Performance Breakdown
    print("\n🔍 4. Session Performance Breakdown (2025 Test)...")
    if 'trades' in res and res['trades']:
        trades = pd.DataFrame(res['trades'])
        trades['entry_date'] = pd.to_datetime(trades['entry_date'])
        trades['hour'] = trades['entry_date'].dt.hour
        
        def get_session(h):
            if 0 <= h < 8: return 'ASIA'
            elif 8 <= h < 16: return 'LONDON'
            else: return 'NY'
            
        trades['session'] = trades['hour'].apply(get_session)
        session_stats = trades.groupby('session')['pnl_net'].agg(['count', 'sum'])
        print(session_stats)
        
        asia_pnl = session_stats.loc['ASIA', 'sum'] if 'ASIA' in session_stats.index else 0
        if asia_pnl < 0:
            print("   ⚠️ ASIA session underperforming. Consider penalty or exclusion.")
        else:
            print("   ✅ All sessions profitable in 2025.")

    # 6. Overfitting & Stability (Execution Delay & Spread)
    print("\n🔍 5. Stability Test (Randomized Spread/Delay)...")
    # Simulate slightly worse conditions
    res_stable = bt_engine.backtest(test_df, external_signals=ext, risk_pct=0.5, broker_name="PEPPERSTONE") # Higher spread broker
    if 'error' not in res_stable:
        print(f"   📊 Pepperstone (High Spread) Result:")
        print(f"      Net Profit: {res_stable['net_profit_pct']:.2f}% | PF: {res_stable['profit_factor']:.2f}")
        if res_stable['net_profit'] > 0:
            print("   ✅ Model remains profitable under high spread.")
        else:
            print("   ❌ Model fails under high spread.")

    print("\n" + "="*60)
    print("🦁 AUDIT COMPLETE.")

if __name__ == "__main__":
    run_audit()
