
"""
GIA Production Engine - DIRECT API EXECUTION
Standard: XAUUSD M15
Sync: Local CSV + Direct OpenAPI 
"""
import time
import sys
import os
import joblib
from datetime import datetime

# Path Fix
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

class MockEncoder:
    def inverse_transform(self, idxs):
        mapping = {0: 'WAIT', 1: 'BUY', 2: 'SELL'}
        return [mapping[i] for i in idxs]

from backend.engine.consensus import TripleConsensusModel
from backend.engine.inference import GoldAnalysisModel
from backend.connectors.ctrader_bridge import CTraderBridge
from colorama import Fore, Style, init

# Initialize Colorama
init(autoreset=True)

# CONFIG
CSV_PATH = r"C:\GIA_DATA\XAUUSD_M15.csv"
READY_FILE = r"C:\GIA_DATA\XAUUSD_M15.ready"

def run_production_engine():
    models_dir = os.path.join(BASE_DIR, 'backend', 'models')
    models = sorted([f for f in os.listdir(models_dir) if f.endswith('.pkl')])
    
    print(f"\n{Fore.CYAN}╔════════════════════════════════════════════════════════╗")
    print(f"║ {Fore.WHITE}      🦁 GIA LIVE COMMAND CENTER - DEMO API          {Fore.CYAN}║")
    print(f"╚════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
    
    print(f"\n {Fore.YELLOW}SELECT EXECUTION MODE:{Style.RESET_ALL}")
    for i, m in enumerate(models):
        print(f"  [{Fore.GREEN}{i+1}{Style.RESET_ALL}] {m:<25}")
    print(f"  [{Fore.GREEN}C{Style.RESET_ALL}] TRIPLE CONSENSUS (v14 + v2_PRO + v2_FLASH)")
    
    choice = input(f"\n {Fore.WHITE}Enter Selection > {Style.RESET_ALL}").strip().upper()
    
    analyzer = None
    is_consensus = False
    
    if choice == 'C':
        analyzer = TripleConsensusModel(models_dir)
        is_consensus = True
        if len(analyzer.models) < 3:
            print(f"{Fore.RED}❌ Error: Consensus requires all 3 models in {models_dir}{Style.RESET_ALL}")
            return
    elif choice.isdigit() and 1 <= int(choice) <= len(models):
        m_path = os.path.join(models_dir, models[int(choice)-1])
        analyzer = GoldAnalysisModel(model_path=m_path)
    else:
        print(f"{Fore.RED}❌ Invalid selection.{Style.RESET_ALL}")
        return

    # 2. Connect to API
    bridge = CTraderBridge(active_strategy_handler=analyzer.strategy if hasattr(analyzer, 'strategy') else None) 
    if not bridge.connect():
        print(f"{Fore.RED}❌ FAILED: Could not connect to cTrader Open API.{Style.RESET_ALL}")
        return

    # State
    last_processed_ts = None
    last_check_time = time.time()
    
    data_folder = r"C:\GIA_DATA"
    m15_ready_path = os.path.join(data_folder, "XAUUSD_M15.ready")
    mode_name = "TRIPLE CONSENSUS" if is_consensus else os.path.basename(analyzer.model_path)
    print(f"\n{Fore.GREEN}🟢 GIA INSTITUTIONAL LIVE [{mode_name}] ACTIVE.{Style.RESET_ALL}")
    print(f"📡 TRIGGER: Strictly M15 Close | PATH: {data_folder}")

    try:
        while True:
            # 1. Real-Time Account Sync
            open_count = bridge.get_open_position_count()
            equity = bridge.current_equity
            
            # 2. STRICT M15 TRIGGER CHECK
            trigger_detected = False
            if os.path.exists(m15_ready_path):
                # Small stability delay to ensure file lock is released by cTrader
                time.sleep(0.2)
                trigger_detected = True
            
            if trigger_detected:
                print(f"\n🔔 [M15 TRIGGER] Detectated XAUUSD_M15.ready")
                
                # --- DATA VALIDATION & SYNC REPORT ---
                sync_status = {"M15": "FAIL", "M30": "FAIL", "H1": "FAIL"}
                sync_times = {"M15": "N/A", "M30": "N/A", "H1": "N/A"}
                
                def get_latest_ts(filename):
                    fpath = os.path.join(data_folder, filename)
                    if not os.path.exists(fpath): return None
                    try:
                        with open(fpath, 'r') as f:
                            lines = f.readlines()
                            if len(lines) < 2: return None
                            last_line = lines[-1].strip()
                            # Check for non-zero OHLC (simple check: length and comma count)
                            if last_line.count(',') < 5: return None
                            ts = last_line.split(',')[0]
                            return ts
                    except: return None

                # Validate M15 (The Boss)
                m15_ts = get_latest_ts("XAUUSD_M15.csv")
                if m15_ts and m15_ts != last_processed_ts:
                    sync_status["M15"] = "OK"
                    sync_times["M15"] = m15_ts
                    last_processed_ts = m15_ts
                    
                    # Check HTFs
                    for tf in ["M30", "H1"]:
                        ts = get_latest_ts(f"XAUUSD_{tf}.csv")
                        if ts:
                            sync_status[tf] = "OK"
                            sync_times[tf] = ts
                        else:
                            sync_status[tf] = "SKIPPED (Outdated/Missing)"

                    # PRINT LOGGING AS REQUESTED
                    print(f"\n{Fore.BLUE}╔════════════ [DATA SYNC] ════════════╗{Style.RESET_ALL}")
                    print(f"║ M15: {sync_status['M15']:<4} | Time: {sync_times['M15']}")
                    print(f"║ M30: {sync_status['M30']:<4} | Time: {sync_times['M30']}")
                    print(f"║ H1 : {sync_status['H1']:<4} | Time: {sync_times['H1']}")
                    print(f"{Fore.BLUE}╚═════════════════════════════════════╝{Style.RESET_ALL}")

                    last_check_time = time.time()

                    if open_count >= 1:
                        print(f"   {Fore.YELLOW}[FILTER] Skipping: Position already open in cTrader.{Style.RESET_ALL}")
                    else:
                        # 3. AI Analysis
                        print(f"   ⌛ Running Triple Consensus Analytics...")
                        res = analyzer.analyze()
                        if res['success']:
                            signal = res['signal']
                            expl = res['explanation']
                            atr = res['atr']
                            size_mult = res.get('sizing_multiplier', 1.0)
                            
                            if is_consensus:
                                brains = res['brains']
                                print(f"   🧠 BRAINS: [Risk: {brains['risk']}] [Core: {brains['core']}] [Flash: {brains['flash']}]")
                            
                            print(f"   📜 STATUS: {Fore.CYAN}{expl}{Style.RESET_ALL}")

                            if signal in ['BUY', 'SELL']:
                                # Risk parameters (Target 1.0% base)
                                risk_amt = equity * (1.0 / 100.0) * size_mult
                                sl_val, tp_val = atr * 2.0, atr * 3.5
                                
                                sl_pips = sl_val * 10
                                tp_pips = tp_val * 10
                                
                                lots = risk_amt / (100 * sl_val)
                                lots = max(0.01, round(lots, 2))

                                print(f"   {Fore.GREEN}🎯 EXECUTION: {signal} {lots} Lots | SL: {round(sl_pips,1)} | TP: {round(tp_pips,1)}{Style.RESET_ALL}")
                                
                                success = bridge.send_market_order(
                                    direction=signal,
                                    lots=lots,
                                    sl_pips=sl_pips,
                                    tp_pips=tp_pips
                                )
                                
                                if success:
                                    print(f"   ✅ SUCCESS: Order sent to OpenAPI.")
                                else:
                                    print(f"   ❌ ERROR: Transmission Failed.")
                        else:
                            print(f"   {Fore.RED}⚠️ Analysis Error: {res.get('error')}{Style.RESET_ALL}")

                    # 4. Mandatory Cleanup of ALL .ready files
                    for rf in [f for f in os.listdir(data_folder) if f.endswith('.ready')]:
                        try: 
                            os.remove(os.path.join(data_folder, rf))
                            print(f"   🧹 Cleaned: {rf}")
                        except: pass
                else:
                    print(f"   ❌ [SYNC ERROR] Latest M15 timestamp rejected or duplicate. Skipping cycle.")
                    # Still clean up to avoid loop
                    for rf in [f for f in os.listdir(data_folder) if f.endswith('.ready')]:
                        try: os.remove(os.path.join(data_folder, rf))
                        except: pass

            if time.time() - last_check_time > 1200: # 20 mins monitor
                print(f"\n{Fore.RED}⚠️ STALL DETECTED: No M15 update for 20 minutes. Check your cTrader CSV Export settings.{Style.RESET_ALL}")
                last_check_time = time.time()

            time.sleep(1) # Frequency of check
            bid = bridge.latest_bid or 0.0
            ask = bridge.latest_ask or 0.0
            print(f"{Fore.WHITE}Heartbeat: {last_processed_ts} | Price: {Fore.YELLOW}{bid:.2f}/{ask:.2f}{Fore.WHITE} | Equity: ${round(equity, 2)} | Pos: {open_count}{Style.RESET_ALL}", end='\r')

    except KeyboardInterrupt:
        print(f"\n{Fore.RED}🛑 Terminating GIA Live Engine...{Style.RESET_ALL}")
        bridge.shutdown()

if __name__ == "__main__":
    run_production_engine()
