
import os
import subprocess
import sys
from colorama import Fore, Style, init

init(autoreset=True)

def print_menu():
    print(f"\n{Fore.CYAN}╔════════════════════════════════════════════════════════╗")
    print(f"║ {Fore.WHITE}          🦁 GIA INSTITUTIONAL MASTER CONTROL          {Fore.CYAN}║")
    print(f"╚════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
    print(f"\n {Fore.YELLOW}ACTIVE OPERATIONS:{Style.RESET_ALL}")
    print(f"  [{Fore.GREEN}1{Style.RESET_ALL}] RUN LIVE DEMO (Trading Console)")
    print(f"  [{Fore.GREEN}2{Style.RESET_ALL}] START PREDATOR TRAINING (Background)")
    print(f"  [{Fore.GREEN}3{Style.RESET_ALL}] RUN BACKTEST ARENA")
    print(f"  [{Fore.GREEN}4{Style.RESET_ALL}] VIEW NEWS CALENDAR STATUS")
    print(f"  [{Fore.GREEN}5{Style.RESET_ALL}] UNIVERSAL MARKET SIMULATOR (Data Generator)")
    print(f"  [{Fore.RED}Q{Style.RESET_ALL}] EXIT")

def main():
    while True:
        print_menu()
        choice = input(f"\n {Fore.WHITE}GIA-Command > {Style.RESET_ALL}").strip().upper()
        
        if choice == '1':
            print(f"\n🚀 Launching Live Console...")
            subprocess.run([sys.executable, "run_live_demo.py"])
        
        elif choice == '2':
            print(f"\n🧠 Starting Neural Training (V12.0 Hyper-Pulse)...")
            # Run in background via start (windows) or & (linux)
            if os.name == 'nt':
                subprocess.Popen(["start", "cmd", "/k", sys.executable, "GIA_SIGNAL_PRO/core/trainer.py"], shell=True)
            else:
                subprocess.Popen([sys.executable, "GIA_SIGNAL_PRO/core/trainer.py", "&"], shell=True)
            print(f"{Fore.GREEN}✅ Training launched in a new terminal unit. You can continue trading here.")
            
        elif choice == '3':
            print(f"\n🎲 Opening Backtest Arena...")
            subprocess.run([sys.executable, "run_backtest.py"])
            
        elif choice == '4':
            from backend.utils.news import NewsGuard
            guard = NewsGuard()
            guard.fetch_news(force=True)
            is_safe, reason = guard.check_safety()
            print(f"\n📡 News Status: {'SAFE' if is_safe else 'DANGER'}")
            if not is_safe: print(f"Reason: {reason}")
            
        elif choice == '5':
            print(f"\n🔌 Opening Universal Market Simulator...")
            launcher_path = os.path.join("backend", "synthetic_data", "launcher.py")
            subprocess.run([sys.executable, launcher_path])
            
        elif choice == 'Q':
            print("Shutting down Master Control...")
            break
        else:
            print(f"{Fore.RED}Invalid Selection.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}🛑 GIA Master Control Terminated. Goodbye!{Style.RESET_ALL}")
        sys.exit(0)
