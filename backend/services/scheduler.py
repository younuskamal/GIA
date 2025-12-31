"""
GIA Scheduler - Automates Data Updates and Model Training
"""
import time
import schedule
import threading
from datetime import datetime
import subprocess
import os
import sys

# Fix imports
BASE_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_BACKEND not in sys.path:
    sys.path.append(BASE_BACKEND)

from data.loaders import fetch_real_gold_data, fetch_real_gold_news

def daily_data_update():
    """Daily task to refresh gold_data.csv."""
    print(f"⏰ [{datetime.now()}] Refreshing Data...")
    try:
        df = fetch_real_gold_data(period="max")
        news = fetch_real_gold_news()
        print(f"✅ Daily Update Done: {len(df) if df is not None else 0} prices, {len(news) if news is not None else 0} news.")
    except Exception as e:
        print(f"❌ Daily Update Error: {e}")

def continuous_training():
    """Runs the Training Pipeline."""
    print(f"⏰ [{datetime.now()}] Starting Continuous Evolutionary Training...")
    try:
        # Correct path to pipeline.py
        pipeline_path = os.path.join(BASE_BACKEND, 'training', 'pipeline.py')
        
        # Run
        result = subprocess.run([sys.executable, pipeline_path], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Evolution Cycle Completed.")
            if "NEW LEADER!" in result.stdout:
                print("✨✨✨ NEW MODEL PROMOTED ✨✨✨")
            else:
                print("ℹ️ Evolution finished. No new champion found.")
        else:
            print(f"❌ Evolution Error:\n{result.stderr}")
            print("STDOUT:", result.stdout)
            
    except Exception as e:
        print(f"❌ Scheduler Error: {e}")

def manual_train_trigger():
    threading.Thread(target=continuous_training).start()
    return {"status": "started"}

def run_scheduler():
    print("🕒 Scheduler Active.")
    # Data often
    schedule.every(6).hours.do(daily_data_update)
    
    # Train Daily at night
    schedule.every().day.at("02:00").do(continuous_training)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    run_scheduler()
