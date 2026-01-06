
"""
GIA Production Engine - DIRECT API EXECUTION
Standard: XAUUSD M15 (LOCKED)
Sync: Local CSV (C:\GIA_DATA) + Direct OpenAPI 
Version: 3.0 (Self-Healing & Risk Selective)
"""
import time
import sys
import os
import json
import logging
from datetime import datetime
from colorama import Fore, Style, init

# Path Fix
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# Initialize Colorama & Logging
init(autoreset=True)
logging.basicConfig(
    filename='live_audit.log',
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)

from backend.engine.consensus import TripleConsensusModel
from backend.engine.inference import GoldAnalysisModel, EliteDuoEngine
from backend.connectors.ctrader_bridge import CTraderBridge
from backend.core.rules import RiskRules
from backend.services.telegram_service import telegram_service

# 🦁 INSTITUTIONAL LOCK: Production Parameters
# 🦁 Project-Centric Path Mapping
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FOLDER = os.path.join(BASE_DIR, 'data')

if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER, exist_ok=True)

ASSET = "XAUUSD"
TIMEFRAME = "M15"

class MockEncoder:
    def inverse_transform(self, idxs):
        mapping = {0: 'WAIT', 1: 'BUY', 2: 'SELL'}
        return [mapping[i] for i in idxs]

import __main__
__main__.MockEncoder = MockEncoder

def get_latest_ts(filename):
    """Safely reads the latest timestamp from a CSV file."""
    fpath = os.path.join(DATA_FOLDER, filename)
    if not os.path.exists(fpath): return None
    try:
        with open(fpath, 'r') as f:
            lines = f.readlines()
            if len(lines) < 2: return None
            last_line = lines[-1].strip()
            if last_line.count(',') < 5: return None
            return last_line.split(',')[0]
    except Exception as e:
        logging.error(f"Error reading {filename}: {str(e)}")
        return None

import argparse

def run_production_engine():
    # 0. Argument Parsing for Server Mode
    parser = argparse.ArgumentParser(description="GIA Institutional Live Engine")
    parser.add_argument('--model_idx', type=str, help='Index of model or C')
    parser.add_argument('--risk', type=float, help='Dynamic Risk %')
    parser.add_argument('--lev', type=int, help='Account Leverage')
    parser.add_argument('--guard', type=int, help='Margin Guard %')
    args = parser.parse_args()

    # 1. Load Models Intelligence
    models_main_dir = os.path.join(BASE_DIR, 'backend', 'models')
    models_pro_dir = os.path.join(BASE_DIR, 'GIA_SIGNAL_PRO', 'models')
    
    models_main = sorted([f for f in os.listdir(models_main_dir) if f.endswith('.pkl')])
    models_pro = sorted([f for f in os.listdir(models_pro_dir) if f.endswith('.pkl')]) if os.path.exists(models_pro_dir) else []
    
    model_paths = {m: os.path.join(models_main_dir, m) for m in models_main}
    for m in models_pro: model_paths[m] = os.path.join(models_pro_dir, m)
    
    all_models = sorted(list(model_paths.keys()))
    
    print(f"\n{Fore.CYAN}╔════════════════════════════════════════════════════════╗")
    print(f"║ {Fore.WHITE}      🦁 GIA LIVE COMMAND CENTER - v3.0 PRO          {Fore.CYAN}║")
    print(f"╚════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
    
    # 2. Institutional Configuration
    if args.model_idx:
        choice = args.model_idx.upper()
        USER_RISK = args.risk if args.risk is not None else 0.5
        LEVERAGE = args.lev if args.lev is not None else 100
        MARGIN_GUARD = args.guard if args.guard is not None else 80
        is_consensus = (choice == 'C')
        
        # Sync to Telegram for dynamic control
        telegram_service.risk = USER_RISK
        telegram_service.leverage = LEVERAGE
        telegram_service.margin_guard = MARGIN_GUARD
    else:
        print(f"{Fore.RED}❌ ERROR: No Model Selected. Use --model_idx [Index or C]{Style.RESET_ALL}")
        return
    
    # The following interactive selection block is removed as per the instruction to only allow --model_idx
    # for i, m in enumerate(all_models):
    #     label = "[PRO]" if "SIGNAL_PRO" in m else "[CORE]"
    #     print(f"  [{Fore.GREEN}{i+1}{Style.RESET_ALL}] {m:<25} {label}")
    # print(f"  [{Fore.GREEN}C{Style.RESET_ALL}] TRIPLE CONSENSUS (v14 + v2_PRO + v2_FLASH)")
    
    # choice = input(f"\n {Fore.WHITE}Enter Selection > {Style.RESET_ALL}").strip().upper()

    # print(f"\n {Fore.YELLOW}STEP 2: RISK & MARGIN PARAMETERS{Style.RESET_ALL}")
    # try:
    #     risk_input = input(f"  [1] Dynamic Risk % per trade (0.1 to 2.0) [Default 0.5] > ").strip()
    #     USER_RISK = float(risk_input) if risk_input else 0.5
        
    #     leverage_input = input(f"  [2] Account Leverage [Default 500] > ").strip()
    #     LEVERAGE = int(leverage_input) if leverage_input else 500
        
    #     margin_input = input(f"  [3] Margin Guard % (Safety Buffer) [Default 100] > ").strip()
    #     MARGIN_GUARD = int(margin_input) if margin_input else 100
    # except ValueError:
    #     print(f"{Fore.RED}⚠️ Invalid numeric input. Reverting to Defaults: Risk 0.5%, Leverage 500, Margin 100%{Style.RESET_ALL}")
    #     USER_RISK, LEVERAGE, MARGIN_GUARD = 0.5, 500, 100

    print(f" {Fore.GREEN}✅ Production Config Locked: Risk {USER_RISK}% | Lev 1:{LEVERAGE} | Guard {MARGIN_GUARD}%{Style.RESET_ALL}")
    
    # 3. Initialize Analysis Engine
    analyzer = None
    # is_consensus is already set above
    
    is_flash_mode = False
    is_duo_mode = False
    if choice == 'C':
        analyzer = TripleConsensusModel(models_main_dir)
    elif choice == 'P':
        analyzer = EliteDuoEngine(models_main_dir)
        is_duo_mode = True
        print(f"   {Fore.CYAN}💎 ELITE DUO ACTIVATED: Harmonizing PRO (M15) & FLASH (M1).{Style.RESET_ALL}")
    elif choice.isdigit() and 1 <= int(choice) <= len(all_models):
        m_name = all_models[int(choice)-1]
        analyzer = GoldAnalysisModel(model_path=model_paths[m_name])
        if "FLASH" in m_name.upper():
            is_flash_mode = True
            global TIMEFRAME
            TIMEFRAME = "M1"
    else:
        print(f"{Fore.RED}❌ ERROR: Invalid Model Selection. Use 1-{len(all_models)}, C or P.{Style.RESET_ALL}")
        return

    # 4. Connect to cTrader Bridge
    bridge = CTraderBridge(active_strategy_handler=analyzer.strategy if hasattr(analyzer, 'strategy') else None) 

    # Start Telegram Listener early for responsiveness
    telegram_service.bridge_ref = bridge # Link bridge for status reporting
    telegram_service.start_listener()
    telegram_service.broadcast("🚀 <b>GIA Institutional Engine Starting...</b>", include_keyboard=True)

    if not bridge.connect():
        print(f"{Fore.RED}❌ FAILED: cTrader OpenAPI Connection Refused. Ensure Proxy/Terminal is running.{Style.RESET_ALL}")
        telegram_service.notify_emergency("cTrader Connection Refused")
        return
    
    telegram_service.broadcast("✅ <b>GIA Connected & Authorized. Monitoring Market...</b>")

    # State Synchronizer
    if not hasattr(run_institutional_engine, 'processed_dict'):
        run_institutional_engine.processed_dict = {"M1": "", "M15": "", "H1": ""}
    
    # Pre-populate with latest timestamps to prevent ghost trades on launch
    run_institutional_engine.processed_dict["M1"] = get_latest_ts(f"{ASSET}_M1.csv") or ""
    run_institutional_engine.processed_dict["M15"] = get_latest_ts(f"{ASSET}_M15.csv") or ""

    last_check_time = time.time()
    last_sync_time = 0
    last_daily_report_day = datetime.now().day
    
    mode_name = "TRIPLE CONSENSUS" if is_consensus else os.path.basename(analyzer.model_path)
    print(f"\n{Fore.GREEN}🟢 GIA INSTITUTIONAL LIVE [{mode_name}] ACTIVE.{Style.RESET_ALL}")
    print(f"📡 MODE: Autonomous API Fetching | PATH: {DATA_FOLDER}")
    logging.info(f"Engine Started | Mode: {choice} | Risk: {USER_RISK}%")

    # Initial Data Sync
    print(f"📡 Requesting Initial Global Market Snapshot...")
    bridge.fetch_live_data()
    time.sleep(2) # Allow sync

    try:
        while True:
            try:
                # 1. Heartbeat & Stability Check
                if not bridge.connected:
                    print(f"\n{Fore.RED}⚠️ CONNECTION LOST! Attempting Self-Healing Reconnect...{Style.RESET_ALL}")
                    if bridge.connect():
                        print(f"{Fore.GREEN}✅ RECONNECTED SUCCESSFULLY.{Style.RESET_ALL}")
                        telegram_service.notify_connection_status(True)
                    else:
                        telegram_service.notify_emergency("Connection Lost - Reconnect Failed")
                        time.sleep(5)
                        continue

                now = datetime.now()
                equity = bridge.current_equity
                open_count = bridge.get_open_position_count()
                
                # 2. AUTONOMOUS TRIGGER & SYNC
                # In DUO mode, we track two triggers (M1 and M15)
                triggers = []
                
                # Auto-sync every 10 seconds
                if time.time() - last_sync_time > 10:
                    sys.stdout.write("\n")
                    bridge.fetch_live_data()
                    last_sync_time = time.time()
                    
                    # 🔔 DUO/PRO PRE-ALERT
                    if now.minute % 15 == 13 and now.second < 15:
                        try:
                            check_analyzer = analyzer.pro if is_duo_mode else analyzer
                            res = check_analyzer.analyze() 
                            if res['success'] and res['signal'] in ['BUY', 'SELL'] and res.get('confidence', 0) > 65:
                                telegram_service.notify_pre_alert(res['signal'], f"Duo-Formation: Strong {res['signal']}", res.get('confidence',0))
                                time.sleep(15)
                        except: pass

                    # Determine what needs to run
                    if is_duo_mode:
                        # M1 Trigger (Flash)
                        if 5 <= now.second <= 25:
                            triggers.append({'tf': 'M1', 'model': analyzer.flash, 'name': 'FLASH'})
                        # M15 Trigger (Pro)
                        if now.minute % 15 == 0 and 5 <= now.second <= 25:
                            triggers.append({'tf': 'M15', 'model': analyzer.pro, 'name': 'PRO'})
                    else:
                        is_triggered = False
                        if TIMEFRAME == "M1":
                            if 5 <= now.second <= 25: is_triggered = True
                        else:
                            if now.minute % 15 == 0 and 5 <= now.second <= 25: is_triggered = True
                        
                        if is_triggered:
                            triggers.append({'tf': TIMEFRAME, 'model': analyzer, 'name': 'SINGLE'})
                for trigger in triggers:
                    target_tf = trigger['tf']
                    active_model = trigger['model']
                    target_csv = f"{ASSET}_{target_tf}.csv"
                    ts = get_latest_ts(target_csv)
                    
                    if ts and ts != run_institutional_engine.processed_dict.get(target_tf):
                        # 🦁 INSTITUTIONAL SAFETY: Ignore old data from before market open
                        try:
                            sig_dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                            if (datetime.now() - sig_dt).total_seconds() > 1800: # Older than 30m
                                run_institutional_engine.processed_dict[target_tf] = ts
                                continue
                        except: pass
                        
                        print(f"\n{Fore.WHITE}{'='*60}")
                        print(f" {Fore.YELLOW}🦁 GIA SIGNAL DETECTED [{trigger['name']}] | TS: {ts} | Equity: ${equity:,.2f}")
                        print(f"{Fore.WHITE}{'='*60}")
                        
                        # A. Run AI Analysis
                        res = active_model.analyze()
                        if res['success']:
                            signal = res['signal']
                            atr = res['atr']
                            size_mult = res.get('sizing_multiplier', 1.0)
                            expl = res['explanation']
                            
                            print(f"   📜 ANALYTICS: {Fore.CYAN}{expl}{Style.RESET_ALL}")
                            logging.info(f"Signal: {signal} | ATR: {atr} | Expl: {expl}")
                            
                            # Notify Telegram on Signal
                            telegram_service.notify_signal_detection(signal, expl, res.get('confidence', 0))

                            if signal in ['BUY', 'SELL'] and open_count < RiskRules.MAX_CONCURRENT_TRADES:
                                # B. Professional Risk Calculation (Dynamic from Telegram)
                                current_risk = telegram_service.risk
                                # 🦁 Duo Risk Override: FLASH always 0.5%
                                if is_duo_mode and trigger['name'] == 'FLASH':
                                    current_risk = 0.5
                                    
                                current_lev = telegram_service.leverage
                                current_guard = telegram_service.margin_guard
                                
                                risk_usd = equity * (current_risk / 100.0) * size_mult
                                sl_val = atr * 2.0
                                tp_val = atr * 3.5
                                sl_pips, tp_pips = sl_val * 10, tp_val * 10
                                lots = max(0.01, round(risk_usd / (100 * sl_val), 2))
                                
                                # C. Margin Check
                                price = bridge.latest_ask if signal == 'BUY' else bridge.latest_bid
                                if price:
                                    margin_req = (price * lots * 100) / current_lev
                                    if equity < (margin_req * (current_guard / 100.0 + 0.5)):
                                        print(f"   {Fore.RED}⚠️ MARGIN GUARD REJECT: Too risky for current equity.{Style.RESET_ALL}")
                                        telegram_service.notify_emergency(f"Margin Reject: {signal} {lots}L rejected by Guard.")
                                        continue

                                # Check if trading is enabled via Telegram
                                if not telegram_service.trading_enabled:
                                    print(f"   {Fore.YELLOW}⏸️ TRADE SKIPPED: Trading is currently DISABLED via Telegram.{Style.RESET_ALL}")
                                    continue

                                # D. Order Transmission
                                print(f"   🎯 EXECUTION: {signal} {lots} Lots | SL: {round(sl_pips,1)} | TP: {round(tp_pips,1)}")
                                bridge.send_market_order(signal, lots, sl_pips, tp_pips)

                        # E. Clean State
                        run_institutional_engine.processed_dict[target_tf] = ts
                        last_check_time = time.time()
                else:
                    # If M15 isn't updated yet, we wait and retry sync
                    pass

                # 3. Status Display (Heartbeat)
                bid, ask = (bridge.latest_bid or 0.0), (bridge.latest_ask or 0.0)
                n_safe, _ = analyzer.strategy.news_guard.check_safety()
                m_safe, _ = analyzer.strategy.market_guard.check_gap_risk()
                
                status_color = Fore.GREEN if n_safe and m_safe else Fore.RED
                safety_txt = "SECURE" if n_safe and m_safe else "PAUSED"
                
                # Clear line and print dashboard
                sys.stdout.write("\r\033[K") # Return carriage and clear current line
                dashboard = f"{Fore.WHITE}LIVE: {ASSET} | {Fore.YELLOW}{bid:>8.2f}/{ask:<8.2f}{Fore.WHITE} | Eq: ${equity:,.2f} | Pos: {open_count} | 🛡️ {status_color}{safety_txt}{Style.RESET_ALL}"
                sys.stdout.write(dashboard)
                sys.stdout.flush()
                
                if time.time() - last_sync_time > 1800: # 30 min stall check based on sync attempt
                    # Only warn if connected but no data
                    if bridge.authorized:
                        logging.warning("System Stall Detect: No Sync in 30 mins.")
                        # telegram_service.notify_emergency("System Stall: No data update for 30 mins") # Slienced for now as it might be false positive if market is closed or slow
                    last_sync_time = time.time() # Reset to avoid spam

                # Daily Report (at 23:55 or if day changed)
                if now.day != last_daily_report_day and now.hour == 23 and now.minute >= 55:
                    # Generic daily report for now, actual PNL should be tracked from positions or bridge
                    telegram_service.send_daily_report(0.0, 0, 0.0) # Placeholder
                    last_daily_report_day = now.day

                time.sleep(1)

            except Exception as e:
                err_msg = f"Internal Loop Error: {str(e)}"
                print(f"{Fore.RED}❌ {err_msg}{Style.RESET_ALL}")
                logging.error(err_msg)
                telegram_service.notify_emergency(err_msg)
                time.sleep(10)

    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⏹️ SHUTTING DOWN MANUALLY...{Style.RESET_ALL}")
        telegram_service.broadcast("⚠️ <b>GIA System: Manual Shutdown</b>")
    except Exception as e:
        err_msg = f"CRITICAL SYSTEM FAILURE: {str(e)}"
        print(f"{Fore.RED}💥 {err_msg}{Style.RESET_ALL}")
        logging.critical(err_msg)
        telegram_service.notify_emergency(err_msg)
    finally:
        bridge.shutdown()
        print("💡 Finalizing Institutional Context...")
        time.sleep(1)
        print("✅ DONE.")

if __name__ == "__main__":
    try:
        run_production_engine()
    except Exception as e:
        print(f"Fatal System Failure: {str(e)}")
