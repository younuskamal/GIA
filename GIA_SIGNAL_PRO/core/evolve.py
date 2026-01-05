
import os
import sys
import time
from datetime import datetime
from colorama import Fore, Style, init

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from GIA_SIGNAL_PRO.core.trainer import GIA_Apex_Distiller

init(autoreset=True)

def run_evolution_loop():
    """
    🔄 GIA SELF-EVOLUTION LOOP
    Continuously retrains the model on the latest available data.
    Ensures the 'Apex Sniper' adapts to changing market regimes.
    """
    print(f"\n{Fore.CYAN}╔════════════════════════════════════════════════════════╗")
    print(f"║ {Fore.WHITE}      🔄 GIA SIGNAL PRO: SELF-EVOLUTION ENGINE        {Fore.CYAN}║")
    print(f"╚════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
    
    trainer = GIA_Apex_Distiller()
    
    # Configuration
    RECHECK_INTERVAL_HOURS = 4 # Retrain every 4 hours
    
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{Fore.YELLOW}[{now}] 🚀 Starting Evolution Cycle...{Style.RESET_ALL}")
        
        try:
            # Execute Training
            trainer.train()
            
            print(f"\n{Fore.GREEN}✅ Evolution Cycle Complete. Sniper Intelligence Updated.{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}Next evolution in {RECHECK_INTERVAL_HOURS} hours...{Style.RESET_ALL}")
            
        except Exception as e:
            print(f"\n{Fore.RED}❌ Evolution Error: {e}{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}Retrying in 30 minutes...{Style.RESET_ALL}")
            time.sleep(1800)
            continue
            
        # Sleep until next cycle
        time.sleep(RECHECK_INTERVAL_HOURS * 3600)

if __name__ == "__main__":
    run_evolution_loop()
