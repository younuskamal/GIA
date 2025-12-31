import sys
import os
import time
import pandas as pd
from datetime import datetime
import json

# Setup path to import backend modules
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.data.loaders import load_history_data
from backend.data.processor import process_raw_data
from backend.engine.backtest import BacktestEngine
from backend.core.registry import ModelManager
from backend.core.rules import SystemMode
from backend.core.broker import BrokerSimulator

# ANSI Colors for Professional UI
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    clear_screen()
    print(f"{Colors.HEADER}{Colors.BOLD}")
    print("="*60)
    print("   🦁 GIA PROFESSIONAL STRATEGY SIMULATOR (CLI V2.2)")
    print("   Offline Mode | cTrader Data | Realistic Broker Simulation")
    print("="*60)
    print(f"{Colors.ENDC}")

def get_input(prompt, default=None, validator=None):
    """Robust input handler with validation."""
    while True:
        p_str = f"{Colors.CYAN}{prompt}{Colors.ENDC}"
        if default is not None:
            p_str += f" [{default}]"
        p_str += ": "
        
        val = input(p_str).strip()
        
        if not val and default is not None:
            return default
            
        if validator:
            try:
                valid_val = validator(val)
                return valid_val
            except Exception as e:
                print(f"{Colors.FAIL}Invalid input: {e}{Colors.ENDC}")
        else:
            if val: return val

def select_option(options, prompt="Select Option"):
    print(f"\n{Colors.UNDERLINE}{prompt}:{Colors.ENDC}")
    for i, opt in enumerate(options):
        print(f"  {Colors.BOLD}{i+1}{Colors.ENDC}. {opt}")
    
    def validate_idx(x):
        idx = int(x) - 1
        if 0 <= idx < len(options):
            return options[idx]
        raise ValueError("Out of range")
        
    return get_input("Enter Number", default=1, validator=validate_idx)

def run_interactive_session():
    print_header()
    
    # 1. Select Timeframe
    print(f"\n{Colors.BLUE}🔹 CONFIGURATION: TIMEFRAME{Colors.ENDC}")
    tf = select_option(['M15', 'H1', 'M30', 'M1'], "Choose Timeframe")
    
    # 2. Select Dates
    print(f"\n{Colors.BLUE}🔹 CONFIGURATION: PERIOD{Colors.ENDC}")
    current_year = datetime.now().year
    start_year = get_input("Start Year", default=2023, validator=int)
    end_year = get_input("End  Year", default=current_year, validator=int)
    
    if start_year > end_year:
        print(f"{Colors.WARNING}⚠️  Swapped years automatically.{Colors.ENDC}")
        start_year, end_year = end_year, start_year

    # 3. Model selection
    print(f"\n{Colors.BLUE}🔹 CONFIGURATION: INTELLIGENCE ENGINE{Colors.ENDC}")
    model_folder = os.path.join(os.getcwd(), 'backend', 'models')
    available_models = [f for f in os.listdir(model_folder) if f.endswith('.pkl')]
    available_models.append("None (Strategy Rules Only)")
    
    model_choice = select_option(available_models, "Select Logic/Model")
    
    if "None" in model_choice:
        active_path = None
    else:
        active_path = os.path.join(model_folder, model_choice)
    
    # 4. Broker Simulation
    print(f"\n{Colors.BLUE}🔹 CONFIGURATION: BROKER ENVIRONMENT{Colors.ENDC}")
    broker = select_option(['VIPER', 'ICMARKETS', 'PEPPERSTONE'], "Select Broker Profile")
    
    # 5. Financial Capital
    print(f"\n{Colors.BLUE}🔹 CONFIGURATION: CAPITAL & RISK{Colors.ENDC}")
    initial_balance = get_input("Starting Balance ($)", default=10000.0, validator=float)
    risk = get_input("Risk per trade (%)", default=0.5, validator=float)
    
    # 6. Simulation Mode
    print(f"\n{Colors.BLUE}🔹 CONFIGURATION: SYSTEM MODE{Colors.ENDC}")
    mode_choice = select_option(['REALISTIC (Strategy)', 'STRESS TEST (High Activity)'], "Select Simulation Mode")
    mode = SystemMode.STRATEGY_TEST_MODE if 'REALISTIC' in mode_choice else SystemMode.STRESS_TEST_MODE

    print_header()
    print(f"{Colors.GREEN}🚀 LAUNCHING SIMULATION...{Colors.ENDC}")
    print(f"   Timeframe: {tf} | Period: {start_year}-{end_year}")
    print(f"   Broker:    {broker} | Capital: ${initial_balance:,.0f}")
    print(f"   Risk:      {risk}% | Mode: {mode_choice}")
    print(f"   Model:     {model_choice}")
    print("-" * 60)
    
    # --- LOGIC START ---
    print(f"\n📂 Loading Data...", end=" ")
    df = load_history_data(timeframe=tf, start_year=start_year, end_year=end_year)
    if df is None or df.empty:
        print(f"{Colors.FAIL}FAILED{Colors.ENDC}")
        return
    print(f"{Colors.GREEN}OK{Colors.ENDC}")
    
    print(f"⚙️  Processing...", end=" ")
    df_processed = process_raw_data(df)
    print(f"{Colors.GREEN}OK{Colors.ENDC}")
    
    engine = BacktestEngine(model_path=active_path)
    if active_path: engine.load_model()
        
    start_time = time.time()
    results = engine.backtest(
        df_processed, 
        broker_name=broker, 
        initial_balance=initial_balance, 
        risk_pct=risk,
        mode=mode
    )
    duration = time.time() - start_time
    
    if "error" in results:
        print(f"\n{Colors.FAIL}❌ SIMULATION ERROR: {results['error']}{Colors.ENDC}")
        return

    # --- PROFESSIONAL REPORT ---
    clear_screen()
    print_header()
    
    net_p = results['net_profit']
    color_pnl = Colors.GREEN if net_p > 0 else Colors.FAIL
    
    print(f"{Colors.BOLD}📊 PERFORMANCE REPORT ({model_choice}){Colors.ENDC}")
    print("-" * 60)
    print(f"💰 Net Profit:      {color_pnl}${net_p:,.2f} ({results['net_profit_pct']:.2f}%){Colors.ENDC}")
    print(f"📉 Max Drawdown:    {Colors.FAIL}{results['max_drawdown']:.2f}%{Colors.ENDC}")
    print(f"🎯 Win Rate:        {Colors.CYAN}{results['win_rate']:.2f}%{Colors.ENDC}")
    print(f"⚖️  Profit Factor:   {Colors.BLUE}{results['profit_factor']:.2f}{Colors.ENDC}")
    print(f"🤝 Total Trades:    {results['total_trades']}")
    print(f"💵 Expectancy:      ${results['expectancy']:.2f}/trade")
    
    # Advanced Stats
    dd_pct = results['max_drawdown']
    calmar = (results['net_profit_pct'] / dd_pct) if dd_pct > 0 else 0
    print(f"💹 Calmar Ratio:    {calmar:.2f}")
    print(f"⏱️  Duration:        {duration:.2f}s")
    print("-" * 60)
    
    print(f"\n{Colors.BOLD}📅 MONTHLY PERFORMANCE (Last 12 Months Available){Colors.ENDC}")
    monthly = results['monthly_breakdown']
    sorted_months = sorted(monthly.keys())[-12:]
    
    print(f"{'Month':<15} | {'PnL ($)':>15} | {'Status':<10}")
    print("-" * 45)
    for m in sorted_months:
        val = monthly[m]
        c = Colors.GREEN if val > 0 else Colors.FAIL
        status = "PROFIT" if val > 0 else "LOSS"
        print(f"{m:<15} | {c}{val:>15,.2f}{Colors.ENDC} | {c}{status:<10}{Colors.ENDC}")
        
    print("-" * 45)
    
    # Validation Based on promotion rules: PF >= 1.8, DD <= 6%
    pf = results['profit_factor']
    dd = results['max_drawdown']
    results['passed_promotion'] = pf >= 1.8 and dd <= 6.0
    
    print(f"\n{Colors.BOLD}🏆 GIA PRODUCTION READINESS SCORE{Colors.ENDC}")
    if results['passed_promotion']:
        print(f"   {Colors.GREEN}✅ PROMOTION QUALIFIED!{Colors.ENDC}")
        print(f"   Model meets strict standards (PF: {pf:.2f} >= 1.8 | DD: {dd:.2f}% <= 6%)")
    elif pf > 1.1:
        print(f"   {Colors.WARNING}⚠️  STABLE BUT NOT PRODUCTION READY{Colors.ENDC}")
        print(f"   Needs higher Profit Factor or lower Drawdown.")
    else:
        print(f"   {Colors.FAIL}❌ HIGH RISK / LOW ALPHA{Colors.ENDC}")
        print("   Strategy does not provide sufficient edge for this period.")

    # Save
    save = get_input("\nSave Results? (y/n)", default="y")
    if save.lower() == 'y':
        output_dir = "backend/results"
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%H%M%S")
        
        # Save CSV Trades
        csv_path = os.path.join(output_dir, f"trades_{tf}_{start_year}_{broker}_{ts}.csv")
        pd.DataFrame(results['trades']).to_csv(csv_path, index=False)
        
        # Helper to convert numpy/special types for JSON
        def make_serializable(obj):
            if isinstance(obj, dict):
                return {k: make_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [make_serializable(i) for i in obj]
            elif hasattr(obj, 'item'): # numpy types
                return obj.item()
            elif isinstance(obj, (pd.Timestamp, datetime)):
                return obj.strftime('%Y-%m-%d %H:%M:%S')
            return obj

        # Save JSON Full Stats
        json_path = os.path.join(output_dir, f"report_{tf}_{start_year}_{broker}_{ts}.json")
        summary = {k:v for k,v in results.items() if k not in ['equity_curve', 'trades']}
        summary['config'] = {'model': model_choice, 'risk': risk, 'balance': initial_balance}
        
        clean_summary = make_serializable(summary)
        
        with open(json_path, 'w') as f:
            json.dump(clean_summary, f, indent=4)
            
        print(f"{Colors.GREEN}💾 Saved CSV:  {csv_path}{Colors.ENDC}")
        print(f"{Colors.GREEN}💾 Saved JSON: {json_path}{Colors.ENDC}")

    input(f"\n{Colors.CYAN}Press Enter to exit...{Colors.ENDC}")

if __name__ == "__main__":
    try:
        run_interactive_session()
    except KeyboardInterrupt:
        print("\n\n👋 Exiting...")
