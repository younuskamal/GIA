
import os
import sys
import time
import joblib
import pandas as pd
import numpy as np
from datetime import datetime
from colorama import Fore, Style, init

from GIA_SIGNAL_PRO.config.settings import MODEL_PATH, DATA_DIR, MIN_CONFIDENCE
from GIA_SIGNAL_PRO.core.trainer import GIA_Apex_Distiller

init(autoreset=True)

class GIASignalEngine:
    """
    🦁 GIA SIGNAL PRO - PREMIUM SCALPING ENGINE
    Standalone, probability-driven intelligence.
    Optimized for M1 entries with multi-TF verification.
    """
    def __init__(self):
        self.model_data = self._load()
        self.trainer = GIA_Apex_Distiller()
        self.last_signal_ts = None
        self.session_memory = [] # Track recent signals for spacing

    def _load(self):
        if os.path.exists(MODEL_PATH):
            print(f"✅ Intelligence Loaded: {MODEL_PATH}")
            return joblib.load(MODEL_PATH)
        else:
            print(f"❌ Model not found at {MODEL_PATH}. Please run training first.")
        return None

    def _get_latest_data(self):
        # Optimized for M1 scalping with 2024-2025 Institutional Data
        def read(tf):
            path = os.path.join(DATA_DIR, f"XAUUSD_{tf}.csv")
            df = pd.read_csv(path)
            df.columns = [c.lower() for c in df.columns]
            df['date'] = pd.to_datetime(df['time'], format='mixed', dayfirst=False)
            return df.sort_values('date', ascending=True)
        
        df1 = read("M1")
        df15 = read("M15")
        dfh1 = read("H1")
        
        # Resample M1 to M5
        df5 = df1.set_index('date').resample('5min').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna().reset_index()
        
        return df1, df5, df15, dfh1

    def run_inference(self):
        if not self.model_data: return None
        
        try:
            df1, df5, df15, dfh1 = self._get_latest_data()
            df = self.trainer.engineer_features(df1, df5, df15, dfh1)
            latest = df.iloc[-1:]
            
            ts = latest['date'].iloc[0]
            if self.last_signal_ts == ts: return None
            self.last_signal_ts = ts
            
            # Feature extraction
            feats = self.model_data['features']
            X = latest[feats]
            
            # XGBoost raw prediction
            raw_probs = self.model_data['model'].predict_proba(X)
            
            # ⚖️ Calibration
            calibrator = self.model_data['calibrator']
            calibrated_probs = calibrator.calibrate(raw_probs)[0]
            
            pred = np.argmax(calibrated_probs) # 0:SKIP, 1:BUY, 2:SELL
            conf = int(calibrated_probs[pred] * 100)
            
            # 🦁 PREMIUM SCALPING LOGIC
            if pred != 0 and conf >= MIN_CONFIDENCE:
                # 🛑 Market Hygiene Filters
                spread_wide = False # Could be integrated if real-time spread data exists
                
                direction = "BUY" if pred == 1 else "SELL"
                
                return {
                    "direction": direction,
                    "confidence": conf,
                    "timestamp": ts,
                    "price": latest['close'].iloc[0]
                }

            return None
            
        except Exception as e:
            print(f"{Fore.RED}❌ Inference Error: {e}")
            return None

    def monitor(self):
        print(f"{Fore.GOLD}🦁 GIA SIGNAL PRO: Live M1 Atomic Monitoring...")
        m1_ready = os.path.join(DATA_DIR, "XAUUSD_M1.ready")
        
        while True:
            if os.path.exists(m1_ready):
                # Stability sleep for atomic write lock
                time.sleep(0.2)
                
                # Run inference on new candle
                signal = self.run_inference()
                
                # Surgical Cleanup
                try:
                    os.remove(m1_ready)
                except: pass
                
                # Feedback
                if not signal:
                    now = datetime.now().strftime("%H:%M:%S")
                    print(f"{Fore.LIGHTBLACK_EX}Heartbeat: {now} | M1 Sync OK | No Signal{Style.RESET_ALL}")
            
            time.sleep(0.5) # Fast poll for M1 accuracy

if __name__ == "__main__":
    engine = GIASignalEngine()
    engine.run_inference()
