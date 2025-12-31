
import os
import sys
from colorama import Fore, init

# Lions don't look back.
# GIA SIGNAL PRO - MASTER TRAINER

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from GIA_SIGNAL_PRO.core.trainer import GIA_Apex_Distiller

def main():
    init(autoreset=True)
    print(f"{Fore.CYAN}🦁 GIA SIGNAL PRO | Institutional Scalper Training")
    print("-" * 50)
    
    try:
        distiller = GIA_Apex_Distiller()
        distiller.train()
        print(f"\n{Fore.GREEN}💎 TRAINING COMPLETE. FINAL MODEL SAVED TO MODELS/GIA_SIGNAL_PRO.pkl")
        
    except Exception as e:
        print(f"{Fore.RED}❌ Training Aborted: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
