
import os
import sys
import joblib
import pandas as pd
import numpy as np
from datetime import datetime

# Add root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from GIA_SIGNAL_PRO.config.settings import MODEL_PATH
from GIA_SIGNAL_PRO.core.trainer import GIA_Apex_Distiller
from GIA_SIGNAL_PRO.core.confidence_calibrator import ConfidenceCalibrator

def recalibrate():
    print("🦁 GIA SIGNAL PRO - CONFIDENCE RECALIBRATION CORE")
    print("="*60)
    
    # 1. Load existing model
    if not os.path.exists(MODEL_PATH):
        print(f"❌ Error: Model not found at {MODEL_PATH}")
        return
    
    print(f"📂 Loading existing intelligence: {MODEL_PATH}")
    m_data = joblib.load(MODEL_PATH)
    booster = m_data['model']
    features = m_data['features']
    
    # 2. Load and Prepare Data
    distiller = GIA_Apex_Distiller()
    df1, df5, df15, dfh1 = distiller.load_data()
    df = distiller.engineer_features(df1, df5, df15, dfh1)
    df = distiller.label_data(df)
    
    # Use a larger sample for calibration to ensure stability
    # We take every 2nd row to cover the entire time range (2024-2025)
    cal_df = df.iloc[::2].copy()
        
    print(f"📊 Calibration pool: {len(cal_df)} observations covering {cal_df['date'].min()} to {cal_df['date'].max()}")
    X_cal = cal_df[features]
    y_cal = cal_df['target']
    
    # 3. Get raw probabilities
    print("🧠 Extracting raw booster probabilities...")
    raw_probs = booster.predict_proba(X_cal)
    
    # 4. Fit Isotonic Calibrator
    print("⚖️ Fitting monotonic Isotonic Regression calibrator...")
    calibrator = ConfidenceCalibrator()
    calibrator.fit(raw_probs, y_cal.values)
    
    # 5. Overwrite model data with new calibrator
    m_data['calibrator'] = calibrator
    m_data['timestamp_recalibrated'] = datetime.now().isoformat()
    m_data['calibration_method'] = 'IsotonicRegression (Monotonic)'
    
    joblib.dump(m_data, MODEL_PATH)
    print(f"✅ FINAL SIGNAL MODEL RECALIBRATED & SAVED: {MODEL_PATH}")
    print("="*60)

if __name__ == "__main__":
    recalibrate()
