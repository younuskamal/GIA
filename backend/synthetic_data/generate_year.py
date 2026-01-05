
import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta

# Path Injection
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from config import SyntheticConfig, AssetProfiles
from regimes import RegimeManager
from market_models import CandleFactory

def aggregate_data(df, interval_mins):
    """Aggregates M1 data into higher timeframes."""
    df['Time'] = pd.to_datetime(df['Time'])
    df.set_index('Time', inplace=True)
    
    agg_logic = {
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }
    
    resampled = df.resample(f'{interval_mins}T', label='left', closed='left').agg(agg_logic)
    resampled.dropna(inplace=True)
    resampled.reset_index(inplace=True)
    resampled['Time'] = resampled['Time'].dt.strftime('%Y-%m-%d %H:%M:%S')
    return resampled

def run_universal_simulator(asset_name=None):
    asset_name = asset_name or SyntheticConfig.ACTIVE_ASSET
    print(f"🦁 GIA Universal Simulator: Launching for {asset_name}...")
    np.random.seed(SyntheticConfig.SEED)
    
    regime_mgr = RegimeManager(asset_name)
    profile = regime_mgr.profile
    current_price = profile['base_price']
    start_dt = datetime.strptime(SyntheticConfig.START_DATE, '%Y-%m-%d %H:%M:%S')
    
    m1_data = []
    # Generate 2 years (2024-2025)
    days_to_gen = 731 
    
    print(f"📊 Simulating 2 Years for {asset_name} (Stress: {SyntheticConfig.STRESS_LEVEL})...")
    
    for day in range(days_to_gen):
        current_day_dt = start_dt + timedelta(days=day)
        
        # Check for Market Closure (Skip Weekends for non-crypto)
        if profile['has_weekends'] and current_day_dt.weekday() >= 5:
            continue
            
        for minute in range(1440):
            ts = current_day_dt + timedelta(minutes=minute)
            
            state = regime_mgr.update()
            sess_mult = regime_mgr.get_session_mult(ts.hour)
            
            candle = CandleFactory.create_candle(
                profile,
                current_price, 
                state['drift'], 
                state['vol'], 
                sess_mult,
                SyntheticConfig.STRESS_LEVEL
            )
            
            candle['Time'] = ts.strftime('%Y-%m-%d %H:%M:%S')
            m1_data.append(candle)
            current_price = candle['Close']

        if day % 60 == 0:
            print(f"   Progress: Day {day}/{days_to_gen}...")

    df_m1 = pd.DataFrame(m1_data)
    os.makedirs(SyntheticConfig.OUTPUT_DIR, exist_ok=True)
    
    # Save MTF Bundle
    tfs = [(1, "M1"), (15, "M15"), (30, "M30"), (60, "H1")]
    for mins, label in tfs:
        print(f"🔄 Exporting {asset_name} {label}...")
        if mins == 1:
            df_tf = df_m1
        else:
            df_tf = aggregate_data(df_m1.copy(), mins)
            
        out_path = os.path.join(SyntheticConfig.OUTPUT_DIR, f"{asset_name}_{label}_SYNTH.csv")
        df_tf.to_csv(out_path, index=False)
        print(f"✅ Generated: {out_path}")

    print(f"\n🏆 SIMULATION COMPLETE: {asset_name} is ready for GIA Backtesting.")

if __name__ == "__main__":
    # If users provide asset as CLI arg
    target = sys.argv[1] if len(sys.argv) > 1 else None
    run_universal_simulator(target)
