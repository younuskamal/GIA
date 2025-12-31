import os
import sys
import time
from colorama import Fore, init, Style
from datetime import datetime

# Add paths
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from GIA_SIGNAL_PRO.config.settings import MIN_CONFIDENCE, DATA_DIR
from GIA_SIGNAL_PRO.core.engine import GIASignalEngine
from GIA_SIGNAL_PRO.utils.telegram_notifier import notifier

def main():
    init(autoreset=True)
    print(f"\n{Fore.CYAN}╔════════════════════════════════════════════════════════╗")
    print(f"║ {Fore.WHITE}      🦁 GIA SIGNAL PRO - TELEGRAM SIGNAL MODE        {Fore.CYAN}║")
    print(f"╚════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
    
    try:
        engine = GIASignalEngine()
        if not engine.model_data:
            print(Fore.RED + "❌ MISSION ABORTED: Model not found. Please run train.py first.")
            return
            
        # Start the Telegram Subscriber Listener (Polling)
        notifier.start_listener()
            
        print(f"{Fore.GREEN}💎 Intelligence Engaged. Monitoring M1 for Opportunities...")
        print(f"📡 Filters: Confidence >= {MIN_CONFIDENCE}%")
        print(f"📂 Data Source: {DATA_DIR}")
        print("-" * 60)

        # Send Startup confirmation to Telegram
        notifier.send_startup_message(MIN_CONFIDENCE)

        m1_ready = os.path.join(DATA_DIR, "XAUUSD_M1.ready")
        
        while True:
            # 1. Event-Driven Trigger (Matches cTrader Bot)
            if os.path.exists(m1_ready):
                time.sleep(0.2) # Stability lock
                
                # Check for signal
                res = engine.run_inference()
                
                # 2. Surgical Cleanup (Don't touch M15/H1 ready files)
                try: 
                    os.remove(m1_ready)
                except: pass
                
                if res:
                    direction = res['direction']
                    conf = res['confidence']
                    ts = res['timestamp']
                    
                    if conf >= MIN_CONFIDENCE:
                        print(f"\n🚀 {Fore.GREEN}SIGNAL CONFIRMED: {direction} ({conf}%) at {ts}")
                        sent = notifier.send_signal(direction, conf, ts)
                        if sent: print(f"   {Fore.BLUE}📨 Telegram: Dispatched.")
                        else: print(f"   {Fore.RED}⚠️ Telegram: Dispatch Failed.")
                
                # Visual Feedback
                now = datetime.now().strftime("%H:%M:%S")
                print(f"{Fore.LIGHTBLACK_EX}Heartbeat: {now} | M1 Atomic Sync: OK | Monitoring...{Style.RESET_ALL}")

            # 3. High-Freq Polling for Scalping Accuracy
            time.sleep(0.5) 
            
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\n🛑 Shutting down GIA SIGNAL PRO...")
        notifier.send_shutdown_message()
    except Exception as e:
        print(Fore.RED + f"\n\nCRITICAL RUNTIME ERROR: {e}")
        notifier.send_shutdown_message()

if __name__ == "__main__":
    main()
